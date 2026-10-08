from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
import pytest
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.registry import Registry
from atima_fl.engine.aggregation import aggregate
from atima_fl.engine.plans import save_defense_study
from atima_fl.engine.statistics import summarize_defenses


def test_defenses_bound_corruption_and_do_not_remove_clients():
    registry = Registry()
    matrix = np.array([[1.0, 2.0], [1.0, 2.0], [1.0, 2.0], [1000.0, -1000.0]])
    mad = registry.get("defense", "coordinate_winsorization")
    bounded, audit = mad.hooks["apply"](matrix.copy(), registry.parameters("defense", mad.id, {}))
    assert bounded.shape == matrix.shape and np.isfinite(bounded).all()
    np.testing.assert_array_equal(bounded[:3], matrix[:3])
    np.testing.assert_allclose(bounded[3], [1.0, 2.0], atol=4e-6)
    assert audit["modified_clients"] == 1 and audit["zero_mad_coordinates"] == 2
    adaptive = registry.get("defense", "adaptive_clipping")
    clipped, audit = adaptive.hooks["apply"](
        matrix, registry.parameters("defense", adaptive.id, {})
    )
    assert np.linalg.norm(clipped[-1]) == pytest.approx(np.sqrt(5))
    assert audit["clipped_clients"] == 1


def test_smoothed_geometric_median_resists_a_single_extreme_outlier():
    c = ExperimentConfig(
        clients=4, aggregation="geometric_median", aggregation_params={"iterations": 100}
    ).validate()
    rows = [[np.array([1.0, 2.0])] for _ in range(3)] + [[np.array([1000.0, -1000.0])]]
    result, audit = aggregate(rows, [1] * 4, c)
    np.testing.assert_allclose(result[0], [1.0, 2.0], atol=1e-5)
    assert audit["converged"]
    # Same-location updates are a zero-distance edge case, not division by zero.
    result, _ = aggregate(rows[:3], [1] * 3, c)
    np.testing.assert_array_equal(result[0], [1.0, 2.0])


def test_pipeline_order_changes_result_and_is_audited():
    rows = [[np.array(v)] for v in [[1.0, 0.0], [0.0, 1.0], [100.0, 100.0]]]
    stages = (
        {"id": "norm_clipping", "params": {"clip_norm": 1.0}},
        {"id": "coordinate_winsorization", "params": {"scale": 1.0}},
    )
    c = ExperimentConfig(clients=3, defenses=stages).validate()
    first, audit = aggregate(rows, [1] * 3, c)
    second, _ = aggregate(rows, [1] * 3, replace(c, defenses=tuple(reversed(stages))))
    assert not np.allclose(first[0], second[0])
    assert [s["id"] for s in audit["defense_stages"]] == [s["id"] for s in stages]


def test_export_defense_quartet_preserves_protocol_and_declares_common_horizon(tmp_path):
    c = ExperimentConfig(
        name="FlipAttack_2026-10-08",
        attack="sign_flip",
        defenses=({"id": "norm_clipping", "params": {}},),
        aggregation="median",
    ).validate()
    root = save_defense_study(c, tmp_path)
    profiles = [ExperimentConfig.load(p) for p in root.glob("plans/*/experiment.toml")]
    assert len(profiles) == 4 and (root / "plan.zip").is_file()
    assert all(p.minimum_rounds == p.rounds == p.paired_rounds == 50 for p in profiles)
    assert len({p.seed for p in profiles}) == 1
    assert sum(bool(p.defenses) for p in profiles) == 2
    for attack in [p for p in profiles if p.attack != "none"]:
        clean = next(p for p in profiles if p.name == Path(attack.paired_clean).name)
        assert attack.pairing_id({}) == clean.pairing_id({})
    with pytest.raises(ValueError, match="Select an attack"):
        save_defense_study(replace(c, attack="none"), tmp_path)


def test_defense_statistics_requires_matching_independent_quartets(tmp_path):
    inputs = []
    for seed, effect in [(1, 0.1), (2, 0.2), (3, 0.3)]:
        row = {
            "seed": seed,
            "status": "complete",
            "protocol": {
                "seed": seed,
                "initial_weights_sha256": str(seed),
                "condition": {"model": "mlp"},
            },
            "protection": {"aggregation": "median"},
            "protection_sources": {"component/aggregator/median": "sha-v1"},
            "reference_sources": {"component/aggregator/fedavg": "sha-f"},
            "attacked_test_macro_f1_recovery": effect,
            "clean_test_macro_f1_change": -0.01,
            "attack_damage_reduction": effect + 0.01,
            "aud_reduction": 1.0,
        }
        path = tmp_path / f"seed{seed}.json"
        path.write_text(json.dumps(row))
        inputs.append(path)
    report = summarize_defenses(inputs, tmp_path / "stats")
    assert report["estimates"]["attacked_test_macro_f1_recovery"]["mean"] == pytest.approx(0.2)
    with pytest.raises(ValueError, match="distinct"):
        summarize_defenses([inputs[0]] * 3, tmp_path / "invalid")
    drift = json.loads(inputs[-1].read_text())
    drift["protection_sources"]["component/aggregator/median"] = "sha-v2"
    inputs[-1].write_text(json.dumps(drift))
    with pytest.raises(ValueError, match="same protocol"):
        summarize_defenses(inputs, tmp_path / "drift")
    row = deepcopy(row)
    row["protection"] = {"aggregation": "krum"}
    inputs[-1].write_text(json.dumps(row))
    with pytest.raises(ValueError, match="same protocol"):
        summarize_defenses(inputs, tmp_path / "mismatch")
