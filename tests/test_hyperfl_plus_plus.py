"""Small CPU checks for the optional HyperFL++ protocol adapter."""

import numpy as np
import pytest
import torch

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.hyperfl import initial_shared_arrays, train_local


def test_hyperfl_is_opt_in_and_preserves_private_head():
    assert ExperimentConfig().training_method == "standard"

    config = ExperimentConfig(
        model="lopez_cnn",
        training_method="hyperfl_plus_plus",
        compute_device="cpu",
        rounds=1,
        local_epochs=2,
        batch_size=2,
        num_classes=3,
        clients=10,
        servers=1,
    ).validate()
    torch.set_num_threads(1)
    shared_before = initial_shared_arrays(config)
    x = np.random.default_rng(3).normal(size=(4, 60)).astype(np.float32)
    y = np.array([0, 1, 2, 1], dtype=np.int64)

    shared_after, private = train_local(
        config, client=0, round_id=1, before=shared_before,
        x=x, y=y, device="cpu", client_state=None,
    )

    assert len(shared_after) == len(shared_before)
    assert all(np.isfinite(value).all() for value in shared_after)
    assert all(np.isfinite(value).all() for value in private.values())
    assert private["__embedding__"].shape == (16,)
    assert private["fc.weight"].shape == (3, 200)
    assert private["fc.bias"].shape == (3,)


def test_hyperfl_rejects_unsupported_model_and_epoch_budget():
    with pytest.raises(ValueError, match="LopezCNN"):
        ExperimentConfig(model="mlp", training_method="hyperfl_plus_plus").validate()
    with pytest.raises(ValueError, match="at least two"):
        ExperimentConfig(
            model="lopez_cnn", training_method="hyperfl_plus_plus", local_epochs=1
        ).validate()
