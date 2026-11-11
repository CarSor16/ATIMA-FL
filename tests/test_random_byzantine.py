"""Byzantine random baseline reproducibility and explicit attack-window behavior."""

from dataclasses import replace

import numpy as np
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.contracts import AttackContext
from atima_fl.engine.attacks import poison_update


def test_random_byzantine_is_reproducible_and_bounded():
    config = ExperimentConfig(
        attack="random_byzantine",
        attack_params={"relative_l2": 3.0},
        malicious_clients=(0,),
        attack_start=1,
        attack_end=2,
    ).validate()
    global_arrays = [np.zeros((4,), dtype=np.float32)]
    local_arrays = [np.array([1, 2, 3, 4], dtype=np.float32)]
    context = AttackContext(
        config=config,
        client=0,
        round_id=1,
        global_arrays=global_arrays,
        local_arrays=local_arrays,
        attackable_indices=(0,),
    )
    first, info = poison_update(context)
    second, _ = poison_update(context)
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_allclose(
        np.linalg.norm(first[0]),
        3.0 * np.linalg.norm(local_arrays[0]),
        rtol=1e-6,
    )
    assert info["attack_applied"]
    benign = replace(config, malicious_clients=(1,)).validate()
    unchanged, audit = poison_update(replace(context, config=benign))
    np.testing.assert_array_equal(unchanged[0], local_arrays[0])
    assert not audit["attack_applied"]
