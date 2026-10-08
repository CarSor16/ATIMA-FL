from pathlib import Path
import json
import os
import numpy as np
import h5py
from atima_fl.core.numerics import check_arrays


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + chr(10), encoding="utf-8")
    os.replace(temporary, path)


def raw_path(run, round_id, client):
    return Path(run) / "client_artifacts" / f"round_{round_id:04d}" / f"client_{client:02d}.npz"


def write_raw(path, local, original_y, trained_y, source_ids, poisoned_indices, metadata):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = {f"layer_{i:03d}": a for i, a in enumerate(local)}
    values.update(
        original_y=original_y,
        trained_y=trained_y,
        source_ids=source_ids,
        poisoned_indices=poisoned_indices,
        metadata=np.array(json.dumps(metadata)),
    )
    with path.with_suffix(".tmp").open("wb") as stream:
        np.savez_compressed(stream, **values)
    os.replace(path.with_suffix(".tmp"), path)


def read_raw(path):
    with np.load(path, allow_pickle=False) as values:
        local = [values[key].copy() for key in sorted(values.files) if key.startswith("layer_")]
        metadata = json.loads(str(values["metadata"]))
        extra = {
            key: values[key].copy()
            for key in ("original_y", "trained_y", "source_ids", "poisoned_indices")
        }
    check_arrays(local)
    return local, metadata, extra


class RoundStorage:
    def __init__(self, path, manifest):
        self.file = h5py.File(path, "x")
        self.file.attrs["manifest_json"] = json.dumps(manifest)
        self.file.attrs["last_valid_round"] = -1
        self.file.flush()

    @staticmethod
    def weights(group, arrays):
        check_arrays(arrays)
        for index, array in enumerate(arrays):
            options = {"compression": "gzip", "compression_opts": 4} if array.ndim else {}
            group.create_dataset(f"layer_{index:03d}", data=array, **options)

    def commit(
        self, round_id, before, after, clients, evaluation, aggregation, valid=True, error=""
    ):
        root = self.file.create_group(f"rounds/round_{round_id:04d}")
        self.weights(root.create_group("global_before"), before)
        if after is not None:
            self.weights(root.create_group("global_after"), after)
        root.attrs["validation_json"] = json.dumps(evaluation, allow_nan=False)
        root.attrs["aggregation_json"] = json.dumps(aggregation, allow_nan=False)
        for client in clients:
            group = root.create_group(f"clients/client_{client['id']:02d}")
            group.attrs["metadata_json"] = json.dumps(client["metadata"], allow_nan=False)
            self.weights(
                group.create_group("local_update"),
                [a.astype(np.float64) - b for a, b in zip(client["raw"], before)],
            )
            self.weights(
                group.create_group("submitted_update"),
                [a.astype(np.float64) - b for a, b in zip(client["sent"], before)],
            )
            for key, value in client["extra"].items():
                group.create_dataset(key, data=value, compression="gzip")
        root.attrs["numerically_valid"] = valid
        root.attrs["error"] = error
        self.file.flush()
        if valid:
            self.file.attrs["last_valid_round"] = round_id
        self.file.flush()

    def close(self):
        self.file.close()
