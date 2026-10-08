from atima_fl.core.numerics import sha256_file
from atima_fl.core.contracts import Component, DataBatch
from pathlib import Path
import json
import numpy as np

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
        self.classes = sorted(self.mapping, key=self.mapping.get)

    def read(self, path):
        import pandas as pd

        frame = pd.read_parquet(path)
        if not set(FEATURES + METADATA) <= set(frame):
            raise ValueError("Missing features or original-label metadata")
        x = frame[FEATURES].to_numpy(dtype=np.float32)
        y = frame.target_id.to_numpy(dtype=np.int64)
        if not len(y) or not np.isfinite(x).all() or not np.isin(y, range(5)).all():
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
            ) or not np.array_equal(y, expected.target_id.to_numpy()):
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
        return {
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


def validate(config, params):
    if config.input_dim != len(FEATURES) or config.num_classes != 5:
        raise ValueError(
            "Prepared EdgeIIoT adapter expects 60 features and the preserved five-class mapping"
        )


def open_dataset(config, params):
    if not config.dataset_root:
        raise ValueError("Select a real prepared EdgeIIoT dataset path before preflight/training")
    return EdgeDataset(config)


PLUGIN = Component(
    "edge_iiot",
    "dataset",
    "EdgeIIoT multiclass-logiat",
    "Loader dei dati preparati: 60 feature, 5 classi; verifica split/shard senza modificare i dati originali.",
    hooks={"validate": validate, "open": open_dataset},
)
