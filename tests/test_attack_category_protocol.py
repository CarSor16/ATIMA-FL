"""One end-to-end paired Flower-protocol smoke scenario for each implemented attack family.

Uses the same synthetic five-class NIDS fixture and serial CPU message grid as
test_protocol. Proves execution/audit wiring, NOT empirical attack effectiveness.
"""

from dataclasses import replace
import json

import h5py
import numpy as np
import pytest
import torch

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.adapters.flower.server import _run_protocol
from test_protocol import SoftwareGrid, dataset  # noqa: F401


CASES = [
    ("data_poisoning", "label_flip", {}),
    ("byzantine_aggregation_disruption", "min_max", {"knowledge": "oracle"}),
    ("targeted_model_poisoning", "local_class_gradient", {"target_class": 0}),
    ("backdoor", "clean_label_trigger", {"target_class": 0, "poison_rate": 1.0}),
    ("protocol_identity", "sample_weight_hijack", {"count_multiplier": 3}),
    ("free_riding_availability", "free_rider", {}),
]


@pytest.mark.parametrize("category,attack,parameters", CASES, ids=[c[0] for c in CASES])
def test_each_attack_category_through_clean_attacked_protocol(
    dataset, tmp_path, category, attack, parameters,
):
    torch.set_num_threads(1)
    clean_config = ExperimentConfig(
        name="clean",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        compute_device="cpu",
        rounds=2,
        minimum_rounds=2,
        paired_rounds=2,
        model_params={"hidden": [8, 4]},
        local_epochs=1,
        attack_start=2,
        malicious_clients=(0, 1),
    ).validate()
    clean = _run_protocol(SoftwareGrid(), clean_config, "cpu")
    attacked_config = replace(
        clean_config,
        name=f"category_{category}",
        attack=attack,
        attack_params=parameters,
        paired_clean=str(clean),
    ).validate()
    attacked = _run_protocol(SoftwareGrid(), attacked_config, "cpu")

    manifest = json.loads((attacked / "manifest.json").read_text())
    assert manifest["status"] == "complete"
    assert manifest["last_valid_round"] == 2
    assert (attacked / "final_metrics.json").is_file()

    with h5py.File(clean / "trajectory.h5") as baseline, h5py.File(
        attacked / "trajectory.h5"
    ) as modified:
        assert modified.attrs["last_valid_round"] == 2
        for key in baseline["rounds/round_0001/global_after"]:
            np.testing.assert_array_equal(
                baseline[f"rounds/round_0001/global_after/{key}"][...],
                modified[f"rounds/round_0001/global_after/{key}"][...],
            )
        for client_id in range(10):
            metadata = json.loads(
                modified[f"rounds/round_0002/clients/client_{client_id:02d}"].attrs[
                    "metadata_json"
                ]
            )
            assert bool(metadata["active"]) == (client_id in (0, 1))

    # Attack-specific assertions intentionally remain in their focused component tests.
    # This test verifies category coverage at the full experiment/protocol boundary.
