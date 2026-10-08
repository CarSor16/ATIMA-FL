"""No dataset download: synthetic fixtures exercise label projection and safety."""
from dataclasses import replace
import json

import numpy as np
import pandas as pd
import pytest

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.label_taxonomy import (
    BINARY_CLASSES,
    FAMILY_CLASSES,
    FINE_CLASSES,
    project_labels,
)
from atima_fl.components.datasets.edge_iiot import FEATURES
from atima_fl.engine.data import open_dataset


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "edge"
    root.mkdir()
    rng = np.random.default_rng(42)
    start = 0
    for split, count in (("train", 30), ("validation", 15), ("test", 15)):
        frame = pd.DataFrame(rng.random((count, 60)).astype(np.float32), columns=FEATURES)
        frame["source_row_id"] = np.arange(start, start + count)
        frame["input_fingerprint"] = [f"row_{i}" for i in range(start, start + count)]
        frame["fine_label"] = [FINE_CLASSES[i % 15] for i in range(count)]
        frame["target_id"] = np.arange(count) % 5
        frame.to_parquet(root / f"{split}_scaled.parquet", index=False)
        start += count
        if split == "train":
            location = root / "iid"
            (location / "clients").mkdir(parents=True)
            assignment = frame[["source_row_id"]].copy()
            assignment["client_id"] = np.arange(count) // 3
            assignment.to_parquet(location / "client_assignment.parquet", index=False)
            for cid in range(10):
                frame.iloc[cid * 3:(cid + 1) * 3].to_parquet(
                    location / "clients" / f"client_{cid:02d}.parquet", index=False
                )
    documents = {
        "feature_schema.json": {"columns": FEATURES},
        "label_mapping.json": {
            "benign": 0, "dos": 1, "infog": 2, "inject": 3, "malware": 4
        },
        "preprocessor.json": {"fixture": True},
        "manifest.json": {"fixture": True},
    }
    for filename, body in documents.items():
        (root / filename).write_text(json.dumps(body))
    return root


@pytest.mark.parametrize("task,names", [
    ("binary", BINARY_CLASSES),
    ("family_6", FAMILY_CLASSES),
    ("fine_15", FINE_CLASSES),
])
def test_tasks_read_same_samples_without_mutating_prepared_labels(prepared, task, names):
    config = ExperimentConfig(
        dataset_root=str(prepared),
        dataset_params={"task": task},
        num_classes=len(names),
    ).validate()
    reader = open_dataset(config)
    train = reader.split("train")
    assert train.y.shape == (30,)
    assert set(train.y) == set(range(len(names)))
    assert train.metadata["fine_labels"] == [FINE_CLASSES[i % 15] for i in range(30)]
    assert reader.audit()["task"] == task
    inspection = reader.inspect()
    assert inspection["task_availability"][task]["available"] is True
    assert sum(inspection["mapped_class_counts"]["train"].values()) == 30
    assert len(inspection["per_client_counts"]) == 10
    assert sum(sum(v.values()) for v in inspection["per_client_counts"].values()) == 30
    legacy = open_dataset(replace(config, dataset_params={"task": "prepared_5"}, num_classes=5))
    np.testing.assert_array_equal(legacy.split("train").y, np.arange(30) % 5)


def test_unknown_fine_label_is_rejected_instead_of_inventing_mapping(prepared):
    train_file = prepared / "train_scaled.parquet"
    train = pd.read_parquet(train_file)
    train.loc[0, "fine_label"] = "unidentified"
    train.to_parquet(train_file, index=False)
    config = ExperimentConfig(
        dataset_root=str(prepared), dataset_params={"task": "binary"}, num_classes=2
    ).validate()
    report = open_dataset(config).inspect()
    assert not report["task_availability"]["binary"]["available"]
    assert report["task_availability"]["binary"]["unknown_source_labels"] == ["unidentified"]
    with pytest.raises(ValueError, match="unknown source labels"):
        open_dataset(config).split("train")


def test_absent_mitm_blocks_six_class_preflight(prepared):
    for cid in range(10):
        path = prepared / "iid" / "clients" / f"client_{cid:02d}.parquet"
        data = pd.read_parquet(path)
        data.loc[data.fine_label == "MITM", "fine_label"] = "DDoS_TCP"
        data.to_parquet(path, index=False)
    for split in ("train", "validation", "test"):
        path = prepared / f"{split}_scaled.parquet"
        data = pd.read_parquet(path)
        data.loc[data.fine_label == "MITM", "fine_label"] = "DDoS_TCP"
        data.to_parquet(path, index=False)
    config = ExperimentConfig(
        dataset_root=str(prepared),
        dataset_params={"task": "family_6"},
        num_classes=6,
    ).validate()
    assert not open_dataset(config).inspect()["task_availability"]["family_6"]["available"]
    with pytest.raises(ValueError, match="does not support family_6"):
        open_dataset(config).audit()


def test_validate_requires_correct_head_dimensions():
    for task, classes in (("binary", 2), ("family_6", 6), ("fine_15", 15)):
        ExperimentConfig(dataset_params={"task": task}, num_classes=classes).validate()
        with pytest.raises(ValueError, match="num_classes"):
            ExperimentConfig(dataset_params={"task": task}, num_classes=5).validate()


def test_label_mapping_rejects_unknown_and_retains_reference_identity():
    np.testing.assert_array_equal(project_labels(FINE_CLASSES, "fine_15"), np.arange(15))
    assert project_labels(["Normal", "MITM"], "binary").tolist() == [0, 1]
    assert project_labels(["Normal", "MITM"], "family_6").tolist() == [0, 3]
    with pytest.raises(ValueError, match="unknown source labels"):
        project_labels(["unknown"], "fine_15")
