"""CPU fitting and federated BatchNorm state compatibility."""

from dataclasses import replace

import numpy as np
import pytest
import torch

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.numerics import check_arrays, weighted_average
from atima_fl.engine.models import arrays, build, probabilities, set_arrays, train


def test_lopez_input_and_deterministic_initialization():
    config = ExperimentConfig(model="lopez_cnn", model_params={}, compute_device="cpu").validate()
    first, second = build(config), build(config)
    assert sum(p.numel() for p in first.parameters()) == 786133
    assert all(np.array_equal(a, b) for a, b in zip(arrays(first), arrays(second)))
    first.eval()
    with torch.inference_mode():
        assert first(torch.zeros(4, 60)).shape == (4, 5)
    with pytest.raises(ValueError, match="60 ordered features"):
        replace(config, input_dim=59).validate()


def test_lopez_local_fit_and_fedavg_preserve_state():
    config = ExperimentConfig(
        model="lopez_cnn", model_params={}, compute_device="cpu", local_epochs=2, batch_size=8
    ).validate()
    torch.set_num_threads(2)
    initial = arrays(build(config))
    rng = np.random.default_rng(19)
    x = rng.random((25, 60), dtype=np.float32)
    y = np.arange(25, dtype=np.int64) % 5
    fitted = [train(initial, x, y, config, cid, 1, "cpu") for cid in (0, 1)]
    assert any(not np.array_equal(a, b) for a, b in zip(initial, fitted[0]))
    deltas = [[a - b for a, b in zip(local, initial)] for local in fitted]
    mean = weighted_average(deltas, [25, 25])
    after = [a + b for a, b in zip(initial, mean)]
    check_arrays(after, initial)
    model = build(config)
    set_arrays(model, after)
    for key, value in model.state_dict().items():
        if key.endswith("running_var"):
            assert torch.all(value > 0)
    assert not any(key.endswith("num_batches_tracked") for key in model.state_dict())
    p = probabilities(after, x, config, "cpu")
    assert np.isfinite(p).all() and np.allclose(p.sum(axis=1), 1)


def test_omitted_batch_counter_preserves_batchnorm_behavior():
    reference = torch.nn.BatchNorm2d(3)
    adapted = torch.nn.BatchNorm2d(3)
    adapted.num_batches_tracked = None
    generator = torch.Generator().manual_seed(9)
    for _ in range(4):
        x = torch.randn(8, 3, 10, 6, generator=generator)
        assert torch.equal(reference(x), adapted(x))
        assert torch.equal(reference.running_mean, adapted.running_mean)
        assert torch.equal(reference.running_var, adapted.running_var)
    reference.eval()
    adapted.eval()
    assert torch.equal(reference(x), adapted(x))
