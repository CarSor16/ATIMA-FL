"""Evaluation on disjoint, stratified per-client slices of the test split.

``evaluation_scope = "slice"`` exists because the historical ``shared`` mode
scores every personalized model on the *same* rows and sums the matrices: the
pooled result is an average over ten models, and no per-client harm can be read
from it. These tests pin the three properties that make the slice mode usable:

* the slices partition the evaluation split exactly (disjoint, covering);
* the partition is stratified by class and deterministic for a seed;
* a slice never contains training rows, so nobody is scored on what it saw.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine import data as data_engine

from test_protocol import dataset as _protocol_dataset


@pytest.fixture
def dataset(tmp_path):
    return _protocol_dataset.__wrapped__(tmp_path)


def _config(dataset, **overrides):
    values = dict(
        name="slice_probe",
        dataset_root=str(dataset),
        output_root=str(Path(dataset).parent / "runs"),
        clients=10,
        model="lopez_cnn",
        training_method="hyperfl_plus_plus",
        compute_device="cpu",
        rounds=1,
        local_epochs=2,
        batch_size=10,
        evaluation_scope="slice",
        seed=11,
    )
    values.update(overrides)
    return ExperimentConfig(**values).validate()


def test_slices_partition_the_split_exactly(dataset):
    config = _config(dataset, clients=3)
    opened = data_engine.open_dataset(config)
    frame, x, y, slices = opened.reader.slices("test", 3, config.seed)

    covered = np.concatenate(slices)
    assert len(covered) == len(frame) == len(y)
    assert len(np.unique(covered)) == len(covered)  # disjoint, no row twice
    assert sorted(covered.tolist()) == list(range(len(frame)))  # and covering

    ids = frame.source_row_id.to_numpy()
    per_client = [set(ids[index].tolist()) for index in slices]
    assert sum(len(part) for part in per_client) == len(ids)
    for first in range(len(per_client)):
        for second in range(first + 1, len(per_client)):
            assert not per_client[first] & per_client[second]


def test_slices_are_stratified_by_class(dataset):
    config = _config(dataset, clients=3)
    opened = data_engine.open_dataset(config)
    frame, x, y, slices = opened.reader.slices("test", 3, config.seed)
    total = np.bincount(y, minlength=5)
    for client, index in enumerate(slices):
        counts = np.bincount(y[index], minlength=5)
        expected = total / 3
        # A class with fewer rows than clients cannot be split perfectly; the
        # tolerance allows that single-row effect only.
        assert np.all(np.abs(counts - expected) <= 1.0), (client, counts, expected)


def test_slices_are_deterministic_and_seed_dependent(dataset):
    config = _config(dataset)
    opened = data_engine.open_dataset(config)
    first = opened.reader.slices("test", 10, config.seed)[3]
    again = data_engine.open_dataset(config).reader.slices("test", 10, config.seed)[3]
    other = opened.reader.slices("test", 10, config.seed + 1)[3]
    for a, b in zip(first, again):
        assert np.array_equal(a, b)
    assert any(not np.array_equal(a, b) for a, b in zip(first, other))


def test_slice_never_reuses_training_rows(dataset):
    config = _config(dataset)
    opened = data_engine.open_dataset(config)
    with pytest.raises(ValueError, match="training split"):
        opened.reader.slices("train", 10, config.seed)
    with pytest.raises(ValueError, match="training split"):
        opened.client_slice("train", 0, 10, config.seed)
    for client in range(config.clients):
        sliced = set(opened.client_slice("test", client, 10, config.seed).source_ids.tolist())
        trained = set(opened.shard(client).source_ids.tolist())
        assert sliced and not sliced & trained


def test_scope_is_rejected_when_unknown(dataset):
    with pytest.raises(ValueError, match="shared or slice"):
        ExperimentConfig(
            model="lopez_cnn", training_method="hyperfl_plus_plus", evaluation_scope="shard"
        ).validate()
    with pytest.raises(ValueError, match="HyperFL"):
        ExperimentConfig(
            evaluation_scope="slice", training_method="standard"
        ).validate()


class SliceGrid:
    """Software Flower grid used to drive a real protocol run on a real dataset."""

    def __init__(self):
        self.private = {}

    def get_node_ids(self):
        return getattr(self, "nodes", [0, 1])

    def send_and_receive(self, messages, timeout):
        from flwr.app import ArrayRecord, ConfigRecord, Message, MetricRecord, RecordDict

        from atima_fl.adapters.flower.client import evaluation_scope, evaluation_split
        from atima_fl.engine.client import submit_local, train_local as train_client_local
        from atima_fl.engine.hyperfl import evaluate_local

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
                opened = data_engine.open_dataset(config)
                _, metadata = evaluate_local(
                    config, client, round_id, before, opened, "cpu",
                    self.private[client], evaluation_split(command), evaluation_scope(command),
                )
                metadata["original_samples"] = len(opened.shard(client).y)
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


def test_slice_scope_end_to_end_pooled_matrix_is_the_sum(dataset, tmp_path):
    import torch

    from atima_fl.adapters.flower.server import _run_protocol

    torch.set_num_threads(1)
    config = _config(dataset, output_root=str(tmp_path / "runs"), rounds=1)
    grid = SliceGrid()
    grid.nodes = list(range(config.clients))
    run = _run_protocol(grid, config, "cpu")
    result = json.loads((run / "final_metrics.json").read_text())["test"]

    assert result["evaluation_scope"] == "slice"
    assert result["samples"] == 20  # the 20-row test fixture, counted once in total
    per_client = result["per_client"]
    assert [entry["client"] for entry in per_client] == list(range(config.clients))
    assert all(entry["evaluation_scope"] == "slice" for entry in per_client)
    total = np.zeros((5, 5), dtype=np.int64)
    for entry in per_client:
        total += np.array(entry["confusion_matrix"], dtype=np.int64)
    assert np.array_equal(total, np.array(result["confusion_matrix"], dtype=np.int64))
    assert sum(entry["samples"] for entry in per_client) == result["samples"]
    assert all(entry["samples"] == 2 for entry in per_client)

    history = json.loads((run / "validation_history.json").read_text())
    assert history[0]["evaluation_scope"] == "slice"
    assert sum(entry["samples"] for entry in history[0]["per_client"]) == history[0]["samples"]


def test_shared_scope_is_still_the_default(dataset, tmp_path):
    """The historical behaviour must not change: 2 models on the same 20 rows."""
    import torch

    from atima_fl.adapters.flower.server import _run_protocol

    torch.set_num_threads(1)
    config = _config(
        dataset, output_root=str(tmp_path / "shared"), rounds=1,
        evaluation_scope="shared",
    )
    grid = SliceGrid()
    grid.nodes = list(range(config.clients))
    run = _run_protocol(grid, config, "cpu")
    result = json.loads((run / "final_metrics.json").read_text())["test"]
    assert result["evaluation_scope"] == "shared"
    assert result["samples"] == 200
    assert all(entry["samples"] == 20 for entry in result["per_client"])
