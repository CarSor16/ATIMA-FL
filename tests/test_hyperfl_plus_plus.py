"""Small CPU checks for the optional HyperFL++ protocol adapter."""

import math

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
    from atima_fl.adapters.flower.client import evaluation_split
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
                        self.private[client], evaluation_split(command),
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
    # Client-level evidence is part of the artifact from now on: the pooled
    # matrix alone cannot say which client paid the damage.
    assert [entry["client"] for entry in result["per_client"]] == [0, 1]
    assert all(len(entry["confusion_matrix"]) == 5 for entry in result["per_client"])
    assert all(
        sum(map(sum, entry["confusion_matrix"])) == 20
        for entry in result["per_client"]
    )
    with h5py.File(run / "trajectory.h5") as trajectory:
        assert len(trajectory["initial"]) == len(trajectory["rounds/round_0001/global_after"])
        stored = json.loads(trajectory["rounds/round_0001"].attrs["validation_json"])
    assert [entry["client"] for entry in stored["per_client"]] == [0, 1]
    assert stored["per_client"][1]["confusion_matrix"] == result["per_client"][1]["confusion_matrix"]
    history = json.loads((run / "validation_history.json").read_text())
    assert [entry["client"] for entry in history[0]["per_client"]] == [0, 1]

    # Per-client telemetry: one row per logical client per round, next to the
    # aggregates. The clean run has no attacker, but every row is complete.
    telemetry = json.loads((run / "client_telemetry.json").read_text())
    assert telemetry["schema"] == "atima_fl.client_telemetry/1"
    assert telemetry["clients"] == 2
    round_one = telemetry["rounds"][0]
    assert round_one["round"] == 1
    assert [row["client"] for row in round_one["clients"]] == [0, 1]
    assert all(row["participated"] for row in round_one["clients"])
    assert all(row["is_malicious"] is False for row in round_one["clients"])
    for row in round_one["clients"]:
        assert row["update_l2"] > 0
        assert 0.0 <= row["local_accuracy"] <= 1.0
        assert math.isfinite(row["local_loss"])
        assert row["local_metrics_split"].startswith("client's own training shard")

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

    # The attacker's own submitted-update norm is now in the artifact. Before,
    # only the mean/max over clients were stored, so the attack strength could
    # not be measured at all.
    attacked_telemetry = json.loads((attacked / "client_telemetry.json").read_text())
    rows = attacked_telemetry["rounds"][-1]["clients"]
    assert [row["client"] for row in rows] == [0, 1]
    malicious = next(row for row in rows if row["client"] == 0)
    honest = next(row for row in rows if row["client"] == 1)
    assert malicious["is_malicious"] is True
    assert malicious["attack_applied"] is True
    assert malicious["attack"] == "local_class_gradient"
    assert malicious["update_l2"] > 0
    assert malicious["attack_telemetry"]["gradient_l2"] > 0
    assert malicious["attack_telemetry"]["local_delta_l2"] > 0
    assert malicious["attack_telemetry"]["knowledge"] == "local_shard_only"
    assert honest["is_malicious"] is False
    assert honest["attack_applied"] is False
    assert honest["attack_telemetry"] == {}
    # One row per client, never a sample: the count is the logical-client count.
    assert telemetry["clients"] == len(rows)


def test_evaluation_split_is_the_dataset_name_not_the_phase(dataset):
    """Regression for job 3127: the validation phase is labelled "validate".

    The dataset split is called "validation" (``validation_scaled.parquet``);
    feeding the phase label to the dataset raised FileNotFoundError and killed
    every HyperFL++ run at the end of round 1.
    """
    from atima_fl.adapters.flower.client import evaluation_split
    from atima_fl.engine import data as data_engine

    config = ExperimentConfig(
        dataset_root=str(dataset),
        clients=10,
        model="lopez_cnn",
        training_method="hyperfl_plus_plus",
        compute_device="cpu",
        rounds=1,
        local_epochs=2,
        batch_size=10,
    ).validate()
    split_data = data_engine.open_dataset(config)

    # Exact payload the server sends for the validation phase (server.py).
    split = evaluation_split({"phase": "validate", "split": "validation"})
    assert split == "validation"
    assert len(split_data.split(split).y) == 20

    # The phase label is not a split name: this is what used to happen.
    with pytest.raises(FileNotFoundError):
        split_data.split("validate")

    assert evaluation_split({"phase": "test", "split": "test"}) == "test"
    with pytest.raises(ValueError):
        evaluation_split({"phase": "validate"})



def test_first_round_private_state_is_seeded_not_none():
    """Round 1 has no stored private state: it must become {}, never None.

    Over the real Flower transport a None here made ``train_local`` discard the
    freshly trained private state and ``_save_private_state`` fail on
    ``sorted(None)``; every HyperFL++ run died at round 1 with
    "TypeError: 'NoneType' object is not iterable". In-process probes never hit
    it because they call the engine directly.
    """
    from atima_fl.adapters.flower.client import (
        _load_private_state,
        _private_state_for_training,
        _save_private_state,
    )

    class FakeContext:
        def __init__(self):
            self.state = {}

    context = FakeContext()
    assert _load_private_state(context) is None
    assert _private_state_for_training(context) == {}

    _save_private_state(context, {"b": np.zeros(2), "a": np.ones(2)})
    loaded = _load_private_state(context)
    assert sorted(loaded) == ["a", "b"]
    assert np.array_equal(loaded["a"], np.ones(2))
    assert sorted(_private_state_for_training(context)) == ["a", "b"]
