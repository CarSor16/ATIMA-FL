from atima_fl.core.numerics import sha256_file
from atima_fl.core.contracts import Component, DataBatch
from pathlib import Path
import json
import numpy as np
from atima_fl.core.label_taxonomy import TASK_CLASSES, task_catalog, project_labels, availability

FEATURES = [
    f"p{packet:02d}_{field}"
    for packet in range(10)
    for field in ("pl", "iat", "dir", "win", "ttl", "flg")
]
METADATA = ["source_row_id", "input_fingerprint", "fine_label", "target_id"]


class _PreparedEdgeData:
    def __init__(self, config):
        self.root = Path(config.dataset_root).resolve()
        self.config = config
        schema = json.loads((self.root / "feature_schema.json").read_text())
        if schema["columns"] != FEATURES:
            raise ValueError("Unexpected input representation/metadata in features")
        self.mapping = json.loads((self.root / "label_mapping.json").read_text())
        if set(self.mapping.values()) != set(range(5)) or len(self.mapping) != 5:
            raise ValueError("Stable five-class mapping required")
        self.task = config.parameters("dataset")["task"]
        self.classes = (
            sorted(self.mapping, key=self.mapping.get)
            if self.task == "prepared_5" else list(TASK_CLASSES[self.task])
        )

    def targets(self, frame):
        raw = frame.target_id.to_numpy(dtype=np.int64)
        if not np.isin(raw, range(5)).all():
            raise ValueError("Invalid legacy target_id values")
        if self.task == "prepared_5":
            return raw
        return project_labels(frame.fine_label, self.task)

    def inspect(self):
        """Read label columns only. Does not change training files or assignments."""
        import pandas as pd

        frames = {}
        for split in ("train", "validation", "test"):
            file = self.root / f"{split}_scaled.parquet"
            data = pd.read_parquet(file, columns=["fine_label", "target_id"])
            frames[split] = data
        observed = {
            split: {str(label): int(count) for label, count in
                    data.fine_label.astype(str).value_counts().sort_index().items()}
            for split, data in frames.items()
        }
        source_labels = sorted(set().union(*(set(values) for values in observed.values())))
        observed_train = list(frames["train"].fine_label.astype(str).unique())
        statuses = {
            task: availability(observed_train, source_labels, task)
            for task in task_catalog()
        }
        statuses["prepared_5"]["available"] = (
            set(frames["train"].target_id.unique()) == set(range(5))
        )
        label_counts = {}
        if statuses[self.task]["available"]:
            for split, data in frames.items():
                target = self.targets(data)
                counts = np.bincount(target, minlength=len(self.classes))
                label_counts[split] = {
                    name: int(count) for name, count in zip(self.classes, counts)
                }
        by_client = {}
        location = partition_location(self.root, self.config)
        for cid in range(self.config.clients):
            file = location / "clients" / f"client_{cid:02d}.parquet"
            labels = pd.read_parquet(file, columns=["fine_label", "target_id"])
            if statuses[self.task]["available"]:
                counts = np.bincount(self.targets(labels), minlength=len(self.classes))
                by_client[str(cid)] = {
                    name: int(count) for name, count in zip(self.classes, counts)
                }
            else:
                by_client[str(cid)] = {
                    str(name): int(count) for name, count in
                    labels.fine_label.astype(str).value_counts().sort_index().items()
                }
        return {
            "dataset": "edge_iiot",
            "dataset_root": str(self.root),
            "partition": self.config.partition,
            "task": self.task,
            "classes": self.classes,
            "reference_tasks": task_catalog(sorted(self.mapping, key=self.mapping.get)),
            "task_availability": statuses,
            "observed_fine_labels": observed,
            "mapped_class_counts": label_counts,
            "per_client_counts": by_client,
            "note": "Counts describe this prepared directory only, not the published dataset.",
        }

    def read(self, path):
        import pandas as pd

        frame = pd.read_parquet(path)
        if not set(FEATURES + METADATA) <= set(frame):
            raise ValueError("Missing features or original-label metadata")
        x = frame[FEATURES].to_numpy(dtype=np.float32)
        y = self.targets(frame)
        if not len(y) or not np.isfinite(x).all():
            raise ValueError("Empty/invalid data")
        return frame, x, y

    def shard(self, client):
        return self.read(
            partition_location(self.root, self.config) / "clients" / f"client_{client:02d}.parquet"
        )

    def split(self, name):
        return self.read(self.root / f"{name}_scaled.parquet")

    def audit(self):
        import pandas as pd

        frames = {name: self.split(name)[0] for name in ("train", "validation", "test")}
        hashes = {}
        for name, frame in frames.items():
            if frame.source_row_id.duplicated().any():
                raise ValueError("Duplicate source row within split")
            hashes[name] = sha256_file(self.root / f"{name}_scaled.parquet")
        for i, a in enumerate(frames):
            for b in list(frames)[i + 1 :]:
                for column in ("source_row_id", "input_fingerprint"):
                    if set(frames[a][column]) & set(frames[b][column]):
                        raise ValueError(f"Split leakage: {a}/{b}/{column}")
                ha = pd.util.hash_pandas_object(frames[a][FEATURES].astype(np.float32), index=False)
                hb = pd.util.hash_pandas_object(frames[b][FEATURES].astype(np.float32), index=False)
                if set(ha) & set(hb):
                    raise ValueError("Float32 model-input overlap across splits")
        assignment_path = partition_location(self.root, self.config) / "client_assignment.parquet"
        assignment = pd.read_parquet(assignment_path)
        if assignment.source_row_id.duplicated().any() or set(assignment.source_row_id) != set(
            frames["train"].source_row_id
        ):
            raise ValueError("Client assignment must cover training exactly once")
        if set(assignment.client_id) != set(range(self.config.clients)):
            raise ValueError("Incomplete logical client IDs")
        counts = {}
        indexed = frames["train"].set_index("source_row_id")
        for client in range(self.config.clients):
            shard_path = (
                partition_location(self.root, self.config)
                / "clients"
                / f"client_{client:02d}.parquet"
            )
            shard, x, y = self.read(shard_path)
            selected = assignment.loc[assignment.client_id == client, "source_row_id"]
            if shard.source_row_id.duplicated().any() or set(shard.source_row_id) != set(selected):
                raise ValueError("Shard/assignment mismatch")
            expected = indexed.loc[shard.source_row_id]
            if not np.array_equal(
                x, expected[FEATURES].to_numpy(dtype=np.float32)
            ) or not np.array_equal(y, self.targets(expected)):
                raise ValueError("Shard/training content mismatch")
            counts[str(client)] = len(shard)
            hashes[f"client_{client}"] = sha256_file(shard_path)
        hashes["assignment"] = sha256_file(assignment_path)
        for name in (
            "feature_schema.json",
            "label_mapping.json",
            "preprocessor.json",
            "manifest.json",
        ):
            hashes[name] = sha256_file(self.root / name)
        if self.task != "prepared_5":
            inspected = availability(
                frames["train"].fine_label.astype(str).unique().tolist(),
                sorted(set().union(*(set(f.fine_label.astype(str)) for f in frames.values()))),
                self.task,
            )
            if not inspected["available"]:
                raise ValueError(
                    f"Prepared dataset does not support {self.task}: "
                    f"missing training classes {inspected['missing_train']}, "
                    f"unknown labels {inspected['unknown_source_labels']}"
                )
        return {
            "task": self.task,
            "hashes": hashes,
            "rows": {k: len(v) for k, v in frames.items()},
            "client_counts": counts,
            "classes": self.classes,
            "capture_disjointness_verified": False,
        }


def partition_location(root, config):
    registry = config.registry()
    plugin = registry.get("partition", config.partition)
    return plugin.hooks["location"](
        root, config, registry.parameters("partition", config.partition, config.partition_params)
    )


class EdgeDataset:
    def __init__(self, config):
        self.reader = _PreparedEdgeData(config)
        self.classes = self.reader.classes

    @staticmethod
    def batch(triple):
        frame, x, y = triple
        return DataBatch(
            x,
            y,
            frame.source_row_id.to_numpy(dtype=np.int64),
            {"fine_labels": frame.fine_label.astype(str).tolist()},
        )

    def shard(self, client):
        return self.batch(self.reader.shard(client))

    def split(self, name):
        return self.batch(self.reader.split(name))

    def audit(self):
        return self.reader.audit()

    def inspect(self):
        return self.reader.inspect()


def validate(config, params):
    task = params["task"]
    expected = 5 if task == "prepared_5" else len(TASK_CLASSES[task])
    if config.input_dim != len(FEATURES) or config.num_classes != expected:
        raise ValueError(
            f"EdgeIIoT {task} requires 60 ordered features and num_classes={expected}"
        )


def task_options():
    return task_catalog()


def open_dataset(config, params):
    if not config.dataset_root:
        raise ValueError("Select a real prepared EdgeIIoT dataset path before preflight/training")
    return EdgeDataset(config)


PLUGIN = Component(
    "edge_iiot",
    "dataset",
    "EdgeIIoT multiclass-logiat",
    "Prepared Edge-IIoT: legacy 5-class or verified binary/6-family/15-type label projection.",
    parameters={
        "task": {
            "type": "string", "default": "prepared_5",
            "choices": ["prepared_5", "binary", "family_6", "fine_15"],
            "description": "Classification task (source labels required for 2/6/15)",
        }
    },
    hooks={"validate": validate, "open": open_dataset, "task_catalog": task_options},
    translations={
        "it": {
            "title": "EdgeIIoT multiclass-logiat",
            "description": "Dati Edge-IIoT: 5 classi legacy o proiezioni verificate a 2/6/15 classi.",
        }
    },
)
