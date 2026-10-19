"""Focused contracts for new poisoning surfaces; not attack-efficacy benchmarks."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from atima_fl.components.attacks.local_class_gradient import PLUGIN as LOCAL_GRADIENT
from atima_fl.components.attacks.local_class_gradient import transform as local_gradient
from atima_fl.components.attacks.sample_weight_hijack import PLUGIN as MASS_HIJACK
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.attacks import reported_samples
from atima_fl.components.aggregators.fedavg import aggregate


def test_count_spoof_is_limited_to_active_malicious_clients():
    c = replace(
        ExperimentConfig(),
        attack="sample_weight_hijack",
        attack_params={"count_multiplier": 4},
        malicious_clients=(0,),
        attack_start=2,
        attack_end=3,
    )
    for client, round_id, expected in [
        (0, 1, 10), (0, 2, 40), (0, 3, 40), (0, 4, 10), (1, 2, 10),
    ]:
        count, evidence = reported_samples(c, client, round_id, 10)
        assert count == expected
        assert evidence["actual_sample_mass"] == 10
        assert evidence["reported_samples"] == expected
        assert evidence["count_spoofed"] == (expected != 10)
    assert "report_count" in MASS_HIJACK.hooks
    with pytest.raises(ValueError, match="positive"):
        reported_samples(c, 0, 2, 0)


def test_fedavg_responds_to_reported_mass_not_a_scaled_update():
    benign = np.array([[0.0], [1.0]])
    original, _ = aggregate(benign, [10, 10], {})
    spoofed, _ = aggregate(benign, [40, 10], {})
    np.testing.assert_allclose(original, [0.5])
    np.testing.assert_allclose(spoofed, [0.2])
    np.testing.assert_array_equal(benign, [[0.0], [1.0]])


def test_local_gradient_requires_local_target_support(monkeypatch):
    pytest.importorskip("torch")
    from atima_fl.engine import data as data_engine

    monkeypatch.setattr(data_engine, "open_dataset", lambda config: SimpleNamespace(
        shard=lambda client: SimpleNamespace(x=np.ones((3, 2), dtype=np.float32),
                                             y=np.array([0, 0, 0], dtype=np.int64))
    ))
    config = SimpleNamespace(
        num_classes=2,
        parameters=lambda kind: {"target_class": 1, "relative_budget": 0.5, "max_examples": 2},
    )
    context = SimpleNamespace(
        config=config, client=0, round_id=2,
        local_arrays=[np.array([1.0])],
        global_arrays=[np.array([0.0])],
    )
    arrays, evidence = local_gradient(context)
    np.testing.assert_array_equal(arrays[0], context.local_arrays[0])
    assert evidence["attack_applied"] is False
    assert evidence["target_support"] == 0
    assert evidence["knowledge"] == "local_shard_only"
    assert "transform" in LOCAL_GRADIENT.hooks


def test_local_gradient_rejects_target_outside_task():
    validate = LOCAL_GRADIENT.hooks["validate"]
    with pytest.raises(ValueError, match="outside"):
        validate(SimpleNamespace(num_classes=2), {"target_class": 2})
