from dataclasses import replace
import json
import numpy as np
import pytest
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.contracts import AttackContext
from atima_fl.core.registry import Registry
from atima_fl.engine.attacks import poison_update, prepare_training
from atima_fl.engine.aggregation import aggregate


def test_hierarchical_sample_weights_routing_and_spawned_workers():
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    from atima_fl.engine.aggregation import aggregate_topology

    c = ExperimentConfig(clients=6, servers=2, client_servers=(0, 0, 0, 0, 1, 1)).validate()
    updates = [[np.array([float(i), 2 * float(i)], dtype=np.float32)] for i in range(6)]
    counts = [1, 3, 2, 7, 1, 11]
    expected, _ = aggregate(updates, counts, c)
    serial, audit = aggregate_topology(updates, counts, c)
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        parallel, _ = aggregate_topology(updates, counts, c, pool)
    np.testing.assert_allclose(serial[0], expected[0], rtol=1e-6)
    np.testing.assert_array_equal(parallel[0], serial[0])
    assert audit["servers"][0]["clients"] == [0, 1, 2, 3]
    assert [s["original_samples"] for s in audit["servers"]] == [13, 12]
    assert audit["coordinator"] == "sample_weighted_server_deltas"


def test_group_defenses_and_robust_aggregation_are_applied_before_coordinator():
    from atima_fl.engine.aggregation import aggregate_topology

    c = ExperimentConfig(
        clients=6,
        servers=2,
        aggregation="median",
        client_servers=(0, 0, 0, 1, 1, 1),
        defenses=({"id": "norm_clipping", "params": {"clip_norm": 10.0}},),
    ).validate()
    updates = [[np.array([float(i)], dtype=np.float32)] for i in [0, 2, 100, 4, 6, 100]]
    result, audit = aggregate_topology(updates, [1] * 6, c)
    np.testing.assert_array_equal(result[0], [4.0])
    assert all(len(s["aggregation"]["defense_stages"]) == 1 for s in audit["servers"])


def test_attack_window_inclusive_and_unselected_clients_never_attack():
    c = ExperimentConfig(
        clients=8,
        servers=2,
        attack="sign_flip",
        malicious_clients=(2, 5, 7),
        attack_start=3,
        attack_end=5,
    ).validate()
    assert c.server_assignment() == (0, 1, 0, 1, 0, 1, 0, 1)
    for cid in range(c.clients):
        for rid in range(1, 8):
            assert AttackContext(c, cid, rid).active == (cid in (2, 5, 7) and 3 <= rid <= 5)
    clean = replace(c, attack="none", attack_params={}, malicious_clients=()).validate()
    assert not any(AttackContext(clean, cid, 4).active for cid in range(8))


@pytest.mark.parametrize("serializer", ["pickle", "cloudpickle"])
def test_validated_configuration_crosses_process_boundary(serializer):
    import importlib
    import subprocess
    import sys

    c = ExperimentConfig(model_params={"hidden": [8, 4]}).validate()
    payload = importlib.import_module(serializer).dumps(c)
    assert b"atima_component_" not in payload
    program = "import sys,pickle; c=pickle.loads(sys.stdin.buffer.read()); assert not hasattr(c,'_component_snapshot'); c.validate(); print(c.model_params['hidden'])"
    result = subprocess.run(
        [sys.executable, "-I", "-c", program], input=payload, capture_output=True, check=True
    )
    assert result.stdout.decode().strip() == "[8, 4]"


def test_one_file_discovery_removal_and_duplicate(tmp_path):
    folder = tmp_path / "aggregatori"
    folder.mkdir()
    file = folder / "custom.py"
    file.write_text(
        "from atima_fl.core.contracts import Component\n"
        "def mean(matrix, counts, params): return matrix.mean(axis=0), {}\n"
        "PLUGIN=Component('custom','aggregator','Custom','Mean',hooks={'aggregate':mean})\n"
    )
    assert Registry(tmp_path).get("aggregator", "custom").title == "Custom"
    config = ExperimentConfig(aggregation="custom", plugin_directory=str(tmp_path))
    config.validate()
    file.unlink()
    with pytest.raises(ValueError, match="Unavailable"):
        config.validate()
    file.write_text(
        "from atima_fl.core.contracts import Component\n"
        "PLUGIN=Component('fedavg','aggregator','Duplicate','',hooks={})\n"
    )
    with pytest.raises(ValueError, match="Duplicate"):
        Registry(tmp_path)


@pytest.mark.parametrize(
    "values",
    [
        {"rounds": 51},
        {"rounds": 0},
        {"seed": True},
        {"attack": "sign_flip", "rounds": 2, "attack_start": 3},
        {"model_params": {"hidden": [0]}},
        {"attack_params": {"unexpected": 1}},
        {"partition": "dirichlet", "partition_params": {"alpha": 0.1}},
        {"learning_rate": float("nan")},
        {"servers": 0},
        {"servers": 11},
        {"servers": True},
        {"servers": 2, "client_servers": [0, 1]},
        {"servers": 2, "client_servers": [0] * 10},
        {"servers": 2, "client_servers": [0, 1] * 4 + [0, 2]},
        {"servers": 3, "aggregation": "krum"},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises((ValueError, TypeError)):
        ExperimentConfig(**values).validate()


def context(attack, params=None, client=0, round_id=2):
    c = ExperimentConfig(attack=attack, attack_params=params or {}, attack_start=2).validate()
    g = [np.array([1.0, 2.0], dtype=np.float32), np.array([3.0], dtype=np.float32)]
    local = [np.array([2.0, 4.0], dtype=np.float32), np.array([7.0], dtype=np.float32)]
    return AttackContext(
        c,
        client,
        round_id,
        g,
        local,
        {i: [v.copy() for v in local] for i in range(10)},
        {i: 10 for i in range(10)},
        (0,),
    )


@pytest.mark.parametrize(
    "attack,params,expected",
    [("sign_flip", {"strength": 2}, [-1.0, -2.0]), ("update_scaling", {"factor": 3}, [4.0, 8.0])],
)
def test_update_equation_and_protected_buffer(attack, params, expected):
    ctx = context(attack, params)
    result, meta = poison_update(ctx)
    np.testing.assert_array_equal(result[0], expected)
    np.testing.assert_array_equal(result[1], ctx.local_arrays[1])
    np.testing.assert_array_equal(ctx.local_arrays[0], [2.0, 4.0])
    assert meta["parameter_scope"] == "trainable_parameters"


def test_gaussian_relative_budget_deterministic():
    ctx = context("gaussian_noise", {"relative_l2": 0.5})
    a, _ = poison_update(ctx)
    b, _ = poison_update(ctx)
    np.testing.assert_array_equal(a[0], b[0])
    assert np.linalg.norm(a[0] - ctx.local_arrays[0]) == pytest.approx(0.5 * np.sqrt(5), rel=1e-6)


def test_feature_clipping_effect_is_recorded_with_zero_noise():
    ctx = context(
        "feature_noise", {"sigma": 0.0, "poison_rate": 1.0, "clip_min": 0.2, "clip_max": 0.3}
    )
    batch = prepare_training(np.full((10, 60), 0.5, dtype=np.float32), np.arange(10) % 5, ctx)
    assert batch.notes["attack_applied"]
    np.testing.assert_array_equal(batch.x[:, :2], np.full((10, 2), 0.3, dtype=np.float32))


@pytest.mark.parametrize(
    "attack", ["random_labels", "feature_noise", "label_flip", "model_replacement"]
)
def test_data_poisoning_roles_determinism_no_mutation(attack):
    ctx = context(
        attack,
        {"poison_rate": 1.0} if attack in ("random_labels", "feature_noise", "label_flip") else {},
    )
    x = np.full((20, 60), 0.5, dtype=np.float32)
    y = np.arange(20) % 5
    batch = prepare_training(x, y, ctx)
    again = prepare_training(x, y, ctx)
    np.testing.assert_array_equal(batch.x, again.x)
    np.testing.assert_array_equal(batch.y, again.y)
    assert np.all(x == 0.5) and np.array_equal(y, np.arange(20) % 5)
    if attack == "random_labels":
        assert np.all(batch.y != y)
    if attack == "feature_noise":
        assert np.array_equal(batch.y, y) and np.all(batch.x[:, 2:] == x[:, 2:])
        assert np.all((batch.x >= 0) & (batch.x <= 1))
    benign = prepare_training(x, y, replace(ctx, client=2))
    before = prepare_training(x, y, replace(ctx, round_id=1))
    np.testing.assert_array_equal(benign.x, x)
    np.testing.assert_array_equal(before.y, y)


@pytest.mark.parametrize("aggregation", ["fedavg", "median", "trimmed_mean", "krum", "multi_krum"])
def test_aggregators_finite_and_defense_pipeline(aggregation):
    c = ExperimentConfig(
        aggregation=aggregation, defenses=({"id": "norm_clipping", "params": {"clip_norm": 1.0}},)
    ).validate()
    updates = [[np.array([float(i), 0], dtype=np.float32)] for i in range(10)]
    values, meta = aggregate(updates, [1] * 10, c)
    assert np.isfinite(values[0]).all() and np.linalg.norm(values[0]) <= 1.00001
    assert len(meta["defense_stages"]) == 1
    with pytest.raises(ValueError, match="counts"):
        aggregate(updates, [float("nan")] * 10, c)


def test_fedavg_sample_weights():
    value, _ = aggregate(
        [[np.array([0.0], dtype=np.float32)], [np.array([4.0], dtype=np.float32)]],
        [3, 1],
        ExperimentConfig(),
    )
    np.testing.assert_array_equal(value[0], [1.0])


def test_alie_zero_bound_is_reported():
    ctx = context("alie")
    result, meta = poison_update(ctx)
    assert meta["z"] == 0 and meta["degenerate_z_range"]
    assert (
        ctx.config.registry()
        .get("attack", "alie")
        .hooks["warnings"](ctx.config, ctx.config.parameters("attack"))
    )


def test_config_toml_roundtrip(tmp_path):
    c = ExperimentConfig(
        model_params={"hidden": [8, 4]}, defenses=({"id": "norm_clipping", "params": {}},)
    ).validate()
    file = tmp_path / "experiment.toml"
    c.save(file)
    assert ExperimentConfig.load(file).resolved() == c.resolved()
    with pytest.raises(FileExistsError):
        c.save(file)


def test_seed_statistics_are_independent_units(tmp_path):
    from atima_fl.engine.statistics import summarize

    files = []
    for seed, effect in enumerate([-0.1, -0.2, -0.3]):
        file = tmp_path / f"{seed}.json"
        file.write_text(
            json.dumps(
                {
                    "summary": {
                        "seed": seed,
                        "status": "complete",
                        "condition_id": "same",
                        "delta_test_macro_f1": effect,
                    }
                }
            )
        )
        files.append(file)
    result = summarize(files, tmp_path / "stats")
    assert result["n_seeds"] == 3 and result["mean_effect"] == pytest.approx(-0.2)
    assert (
        result["bootstrap_percentile_95_ci"][0] <= -0.2 <= result["bootstrap_percentile_95_ci"][1]
    )
    with pytest.raises(ValueError, match="Duplicate"):
        summarize([files[0]] * 3, tmp_path / "bad")
    with pytest.raises(ValueError, match="three"):
        summarize(files[:2], tmp_path / "bad")
