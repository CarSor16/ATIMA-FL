"""Focused behavior checks for independent threat mechanisms."""
from dataclasses import replace
import json
import numpy as np
import pytest
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.contracts import AttackContext
from atima_fl.core.registry import Registry
from atima_fl.engine.attacks import prepare_training, poison_update
from atima_fl.engine.storage import raw_path, write_raw

def ctx(attack, params=None, *, malicious=(0, 1), client=0, round_id=3):
    config = ExperimentConfig(attack=attack, attack_params=params or {},
                              malicious_clients=malicious, attack_start=2).validate()
    global_arrays = [np.array([1., 2.], dtype=np.float32)]
    local = [np.array([2., 3.], dtype=np.float32)]
    context = AttackContext(config, client, round_id, global_arrays, local,
                            {0: [np.array([2., 3.], dtype=np.float32)],
                             1: [np.array([4., 5.], dtype=np.float32)]}, {i: 10 for i in range(10)}, (0,))
    return context

def test_registration_and_existing_catalog_preserved():
    ids = set(Registry().components["attack"])
    assert {"class_withholding", "clean_label_trigger", "free_rider",
            "stale_replay", "sybil_collusion", "label_flip", "fang", "alie"} <= ids

def test_class_withholding_is_deterministic_and_keeps_labels_unchanged():
    c = ctx("class_withholding", {"target_class": 1, "remove_fraction": 1})
    x = np.ones((12, 60), dtype=np.float32)
    y = np.array([0, 1] * 6)
    a = prepare_training(x, y, c)
    b = prepare_training(x, y, c)
    assert len(a.y) == 6 and (a.y == 0).all()
    np.testing.assert_array_equal(a.x, b.x)
    assert a.notes["withheld_samples"] == 6
    np.testing.assert_array_equal(y, [0, 1] * 6)

def test_clean_label_trigger_changes_features_not_labels():
    c = ctx("clean_label_trigger", {"target_class": 0, "poison_rate": 1})
    x = np.zeros((12, 60), dtype=np.float32)
    y = np.array([0, 1] * 6)
    a = prepare_training(x, y, c)
    np.testing.assert_array_equal(a.y, y)
    assert a.notes["attack_applied"]
    assert np.all(a.x[y == 0, :2] == 0.9)
    assert np.all(a.x[y == 1, :2] == 0)

def test_free_rider_zero_delta():
    c = ctx("free_rider")
    submitted, notes = poison_update(c)
    np.testing.assert_array_equal(submitted[0], c.global_arrays[0])
    assert notes["free_rider_zero_update"] and notes["attack_applied"]

def test_sybil_collusion_copies_leader_and_preserves_benign():
    c = ctx("sybil_collusion", client=1)
    submitted, notes = poison_update(c)
    np.testing.assert_array_equal(submitted[0], [2, 3])
    assert notes["collusion_leader"] == 0
    assert notes["attack_applied"]
    benign = replace(c, client=2)
    result, metadata = poison_update(benign)
    np.testing.assert_array_equal(result[0], benign.local_arrays[0])
    assert not metadata["attack_applied"]

def test_replay_requires_previous_audited_snapshot(tmp_path):
    c = ctx("stale_replay")
    c.run_dir = tmp_path
    path = raw_path(tmp_path, 2, 0)
    write_raw(path, [np.array([8., 9.], dtype=np.float32)],
              np.array([0, 1]), np.array([0, 1]), np.array([0, 1]),
              np.array([], dtype=np.int64), {"client": 0, "round": 2})
    result, notes = poison_update(c)
    np.testing.assert_array_equal(result[0], [8, 9])
    assert notes["replay_source_round"] == 2
    with pytest.raises(ValueError, match="earlier"):
        ExperimentConfig(attack="stale_replay", attack_start=1).validate()
    c.run_dir = tmp_path / "missing"
    with pytest.raises(ValueError, match="unavailable"):
        poison_update(c)
