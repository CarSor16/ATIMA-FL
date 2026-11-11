"""Small CPU checks for the optional HyperFL++ protocol adapter."""

import numpy as np
import pytest
import torch

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.hyperfl import initial_shared_arrays, train_local

from test_protocol import dataset as _protocol_dataset


@pytest.fixture
def dataset(tmp_path):
    return _protocol_dataset.__wrapped__(tmp_path)


def test_hyperfl_is_opt_in_and_preserves_private_head():
    assert ExperimentConfig().training_method == "standard"

    config = ExperimentConfig(
        model="lopez_cnn",
        training_method="hyperfl_plus_plus",
        compute_device="cpu",
        rounds=1,
        local_epochs=2,
        batch_size=2,
        num_classes=5,
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
    assert private["fc.weight"].shape == (5, 200)
    assert private["fc.bias"].shape == (5,)


def test_hyperfl_rejects_unsupported_model_and_epoch_budget():
    with pytest.raises(ValueError, match="LopezCNN"):
        ExperimentConfig(model="mlp", training_method="hyperfl_plus_plus").validate()
    with pytest.raises(ValueError, match="at least two"):
        ExperimentConfig(
            model="lopez_cnn", training_method="hyperfl_plus_plus", local_epochs=1
        ).validate()


def test_hyperfl_one_round_uses_persistent_client_state(dataset, tmp_path):
    import json
    from pathlib import Path

    import h5py
    from flwr.app import ArrayRecord, ConfigRecord, Message, MetricRecord, RecordDict

    from atima_fl.adapters.flower.server import _run_protocol
    from atima_fl.engine import data as data_engine
    from atima_fl.engine.client import submit_local, train_local as train_client_local
    from atima_fl.engine.hyperfl import evaluate_local

    class Grid:
        def __init__(self):
            self.private = {}

        def get_node_ids(self):
            return [0, 1]

        def send_and_receive(self, messages, timeout):
            for message in messages:
                command = message.content["config"]
                config = ExperimentConfig.from_dict(json.loads(command["config_json"]))
                client = int(message.metadata.dst_node_id)
                round_id = int(command["server-round"])
                before = message.content["arrays"].to_numpy_ndarrays()
                phase = command["phase"]
                if phase == "train":
                    state = self.private.setdefault(client, {})
                    values, metadata = train_client_local(
                        config, Path(command["run_dir"]), client, round_id, before,
                        data_engine.open_dataset(config), "cpu", client_state=state,
                    )
                elif phase == "submit":
                    counts = {int(k): int(v) for k, v in json.loads(command["counts_json"]).items()}
                    values, metadata = submit_local(
                        config, Path(command["run_dir"]), client, round_id, before, counts,
                        client_state=self.private.get(client),
                    )
                else:
                    data = data_engine.open_dataset(config)
                    _, metadata = evaluate_local(
                        config, client, round_id, before, data, "cpu",
                        self.private[client], command["split"],
                    )
                    metadata["original_samples"] = len(data.shard(client).y)
                    values = before
                yield Message(
                    content=RecordDict({
                        "arrays": ArrayRecord(numpy_ndarrays=values),
                        "metrics": MetricRecord({
                            "client-id": client,
                            "num-examples": metadata["original_samples"],
                        }),
                        "audit": ConfigRecord({
                            "metadata_json": json.dumps(metadata, allow_nan=False),
                        }),
                    }),
                    reply_to=message,
                )

    import pandas as pd

    train = pd.read_parquet(dataset / "train_scaled.parquet").iloc[:20].copy()
    train.to_parquet(dataset / "train_scaled.parquet", index=False)
    partition = dataset / "iid"
    clients = partition / "clients"
    for file in clients.glob("client_*.parquet"):
        file.unlink()
    assignment = train[["source_row_id"]].copy()
    assignment["client_id"] = np.repeat([0, 1], 10)
    assignment.to_parquet(partition / "client_assignment.parquet", index=False)
    for client in range(2):
        train.iloc[client * 10 : (client + 1) * 10].to_parquet(
            clients / f"client_{client:02d}.parquet", index=False
        )

    torch.set_num_threads(1)
    config = ExperimentConfig(
        name="hyperfl_protocol",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        clients=2,
        model="lopez_cnn",
        training_method="hyperfl_plus_plus",
        compute_device="cpu",
        rounds=1,
        local_epochs=2,
        batch_size=10,
    ).validate()
    run = _run_protocol(Grid(), config, "cpu")
    manifest = json.loads((run / "manifest.json").read_text())
    result = json.loads((run / "final_metrics.json").read_text())["test"]

    assert manifest["status"] == "complete"
    assert manifest["last_valid_round"] == 1
    assert result["personalized_models"] == 2
    assert result["samples"] == 40  # shared 20-row test split evaluated by both local models
    assert sum(map(sum, result["confusion_matrix"])) == 40
    with h5py.File(run / "trajectory.h5") as trajectory:
        assert len(trajectory["initial"]) == len(trajectory["rounds/round_0001/global_after"])

    paired_config = ExperimentConfig(
        name="hyperfl_lcg_clean",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "paired_runs"),
        clients=2,
        model="lopez_cnn",
        training_method="hyperfl_plus_plus",
        compute_device="cpu",
        rounds=2,
        local_epochs=2,
        batch_size=10,
    ).validate()
    clean = _run_protocol(Grid(), paired_config, "cpu")
    attacked_config = ExperimentConfig.from_dict({
        **paired_config.resolved(),
        "name": "hyperfl_lcg_attacked",
        "attack": "local_class_gradient",
        "attack_params": {"target_class": 0, "relative_budget": 0.5, "max_examples": 4},
        "malicious_clients": [0],
        "attack_start": 2,
        "attack_end": 2,
        "paired_clean": str(clean),
    })
    attacked = _run_protocol(Grid(), attacked_config, "cpu")
    attacked_manifest = json.loads((attacked / "manifest.json").read_text())
    assert attacked_manifest["status"] == "complete"
    with h5py.File(attacked / "trajectory.h5") as trajectory:
        client = trajectory["rounds/round_0002/clients/client_00"]
        metadata = json.loads(client.attrs["metadata_json"])
        assert metadata["attack_applied"] is True
        assert metadata["knowledge"] == "local_shard_only"
        assert metadata["target_support"] > 0
        assert metadata["added_perturbation_l2_budget"] > 0
        assert metadata["local_target_loss_after"] > metadata["local_target_loss_before"]
        assert metadata["submitted_differs_from_local"] is True
        for key in client["local_update"]:
            assert not np.array_equal(
                client[f"local_update/{key}"][...],
                client[f"submitted_update/{key}"][...],
            )
