"""Dataset-independent prepared tabular adapter. Import-safe without training extras."""
import hashlib
import json

import numpy as np
from atima_fl.core.contracts import Component, DataBatch
from atima_fl.core.dataset_paths import resolve_dataset_root
from atima_fl.core.numerics import sha256_file


class UniversalTabularDataset:
    def __init__(self, config):
        self.config = config
        self.root = resolve_dataset_root(config.dataset_root)
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest.get("format") != "atima-universal-tabular-v1":
            raise ValueError("Not an ATIMA universal prepared dataset")
        self.mapping = json.loads((self.root / "label_mapping.json").read_text(encoding="utf-8"))
        if not self.mapping or set(self.mapping.values()) != set(range(len(self.mapping))):
            raise ValueError("Invalid class mapping")
        self.schema = json.loads((self.root / "feature_schema.json").read_text(encoding="utf-8"))
        self.features = self.schema["columns"]
        if not self.features or len(set(self.features)) != len(self.features):
            raise ValueError("Invalid feature schema")
        self.task = config.parameters("dataset")["task"]
        self.classes = (["Benign", "Attack"] if self.task == "binary"
                        else sorted(self.mapping, key=self.mapping.get))
        if self.task == "binary" and self.manifest.get("benign_label") not in self.mapping:
            raise ValueError("Binary task needs an explicitly confirmed benign class")
        if config.input_dim != len(self.features) or config.num_classes != len(self.classes):
            raise ValueError(
                f"Prepared dataset requires input_dim={len(self.features)} and "
                f"num_classes={len(self.classes)} for {self.task}"
            )
        if config.clients != self.manifest["clients"]:
            raise ValueError("Prepared shard count differs from configured clients")

    def _read(self, path):
        import pandas as pd

        frame = pd.read_parquet(path)
        required = set(self.features) | {
            "source_row_id", "input_fingerprint", "fine_label", "target_id"
        }
        if not required <= set(frame):
            raise ValueError(f"Missing prepared fields: {sorted(required - set(frame))}")
        x = frame[self.features].to_numpy(dtype=np.float32)
        fine = frame["fine_label"].astype(str).to_numpy()
        if not len(x) or not np.isfinite(x).all():
            raise ValueError("Empty or nonfinite prepared split/shard")
        expected = np.array([self.mapping.get(v, -1) for v in fine], dtype=np.int64)
        stored = frame["target_id"].to_numpy(dtype=np.int64)
        if (expected < 0).any() or not np.array_equal(expected, stored):
            raise ValueError("Prepared label mapping mismatch")
        y = ((fine != self.manifest["benign_label"]).astype(np.int64)
             if self.task == "binary" else stored)
        if any(hashlib.sha256(row.tobytes()).hexdigest() != value for row, value in
               zip(x, frame["input_fingerprint"])):
            raise ValueError("Prepared features differ from stored fingerprints")
        return DataBatch(
            x, y, frame.source_row_id.to_numpy(dtype=np.int64),
            {"fine_labels": fine.tolist()}
        ), frame

    def split(self, name):
        if name not in {"train", "validation", "test"}:
            raise ValueError("Unknown split")
        return self._read(self.root / f"{name}_scaled.parquet")[0]

    def shard(self, client):
        if type(client) is not int or not 0 <= client < self.config.clients:
            raise ValueError("Invalid client ID")
        # Reuse the existing partition plugins, including their parameter validation.
        registry = self.config.registry()
        partition = registry.get("partition", self.config.partition)
        base = partition.hooks["location"](
            self.root, self.config,
            registry.parameters("partition", self.config.partition, self.config.partition_params)
        )
        return self._read(base / "clients" / f"client_{client:02d}.parquet")[0]

    def audit(self):
        import pandas as pd

        hashes = {}
        by_split = {}
        all_ids = set()
        all_fingerprints = set()
        for split in ("train", "validation", "test"):
            batch, frame = self._read(self.root / f"{split}_scaled.parquet")
            ids = batch.source_ids.tolist()
            if len(set(ids)) != len(ids) or set(ids) & all_ids:
                raise ValueError("Cross-split source identity leakage")
            all_ids.update(ids)
            fingerprints = set(frame.input_fingerprint)
            if fingerprints & all_fingerprints:
                raise ValueError("Cross-split feature overlap")
            all_fingerprints.update(fingerprints)
            hashes[split] = sha256_file(self.root / f"{split}_scaled.parquet")
            by_split[split] = batch
        registry = self.config.registry()
        part = registry.get("partition", self.config.partition)
        folder = part.hooks["location"](
            self.root, self.config,
            registry.parameters("partition", self.config.partition, self.config.partition_params)
        )
        assignment = pd.read_parquet(folder / "client_assignment.parquet")
        if set(assignment) != {"source_row_id", "client_id"}:
            raise ValueError("Invalid partition assignment schema")
        if assignment.source_row_id.duplicated().any():
            raise ValueError("Repeated client assignment")
        if set(assignment.source_row_id) != set(by_split["train"].source_ids):
            raise ValueError("Client assignment does not cover training")
        if set(assignment.client_id) != set(range(self.config.clients)):
            raise ValueError("Missing client")
        train, _ = self._read(self.root / "train_scaled.parquet")
        index = {int(row): i for i, row in enumerate(train.source_ids)}
        sizes = {}
        for cid in range(self.config.clients):
            shard_file = folder / "clients" / f"client_{cid:02d}.parquet"
            shard, _ = self._read(shard_file)
            selected = assignment.loc[assignment.client_id == cid, "source_row_id"]
            if len(shard.y) != len(selected) or set(shard.source_ids) != set(selected):
                raise ValueError("Shard/assignment mismatch")
            expected_indices = [index[int(row)] for row in shard.source_ids]
            if not np.array_equal(shard.x, train.x[expected_indices]) or not np.array_equal(
                shard.y, train.y[expected_indices]
            ):
                raise ValueError("Shard/train feature or label mismatch")
            sizes[str(cid)] = len(shard.y)
            hashes[f"client_{cid}"] = sha256_file(shard_file)
        hashes["assignment"] = sha256_file(folder / "client_assignment.parquet")
        for name in ("feature_schema.json", "label_mapping.json",
                     "preprocessor.json", "manifest.json"):
            hashes[name] = sha256_file(self.root / name)
        return {
            "task": self.task, "hashes": hashes,
            "rows": {key: len(value.y) for key, value in by_split.items()},
            "client_counts": sizes, "classes": self.classes,
            "capture_disjointness_verified": False,
            "source_schema": "tabular, training-only preprocessing",
        }

    def inspect(self):
        counts = {}
        for split in ("train", "validation", "test"):
            y = self.split(split).y
            counts[split] = {
                label: int((y == index).sum()) for index, label in enumerate(self.classes)
            }
        class_names = sorted(self.mapping, key=self.mapping.get)
        available = {
            "multiclass": {
                "available": True, "num_classes": len(class_names),
                "class_names": class_names,
            },
            "binary": {
                "available": self.manifest.get("benign_label") in self.mapping,
                "num_classes": 2, "class_names": ["Benign", "Attack"],
            },
        }
        return {
            "dataset": "universal_tabular", "dataset_root": str(self.root),
            "task": self.task, "classes": self.classes, "input_dim": len(self.features),
            "task_availability": available, "mapped_class_counts": counts,
            "reference_tasks": available, "per_client_counts": {},
            "note": "Class labels confirmed during local preparation; not inferred from names.",
        }


def open_dataset(config, params):
    return UniversalTabularDataset(config)


def validate(config, params):
    if params["task"] == "binary" and config.num_classes != 2:
        raise ValueError("Binary classification requires num_classes=2")
    # Multiclass cardinality and feature schema are verified at execution preflight.


def task_catalog():
    # Dynamic cardinality is read from the prepared directory during local inspection.
    return {
        "multiclass": {
            "description": "Dynamic class list from prepared dataset",
            "num_classes": 2, "class_names": ["Inspect dataset to load real labels"],
        },
        "binary": {
            "description": "Requires a human-confirmed benign label",
            "num_classes": 2, "class_names": ["Benign", "Attack"],
        },
    }


PLUGIN = Component(
    "universal_tabular", "dataset", "Universal tabular (prepared)",
    "CSV/CSV.GZ/Parquet sources converted by the local Dataset Manager; "
    "dataset-specific column assumptions are not required.",
    parameters={"task": {"type": "string", "default": "multiclass",
                         "choices": ["multiclass", "binary"]}},
    hooks={"open": open_dataset, "validate": validate, "task_catalog": task_catalog},
    limitations="Only prepared tabular data. Dynamic feature/class dimensions must match manifest. "
                "Binary requires a confirmed benign class.",
)
