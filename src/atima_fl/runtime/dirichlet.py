"""Deterministically prepare persisted non-IID Dirichlet client shards.

Run on an authorized host with the full prepared Edge-IIoT dataset.
The training, validation and test splits are never rewritten.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from atima_fl.components.partitions.dirichlet import alpha_directory


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_dirichlet(dataset_root, *, alpha, clients, seed=2026):
    """Create one never-overwritten, deterministic Dirichlet partition.

    Returns the target directory. Requires pandas and pyarrow (Runtime extras).
    The distribution is sampled per original prepared_5 target class.
    """
    import pandas as pd

    alpha_value = alpha_directory(alpha)
    if type(clients) is not int or not 2 <= clients <= 256:
        raise ValueError("Dirichlet client count must be an integer in [2, 256]")
    if type(seed) is not int or seed < 0:
        raise ValueError("Dirichlet seed must be a non-negative integer")
    root = Path(dataset_root).expanduser().resolve(strict=True)
    source = root / "train_scaled.parquet"
    if not source.is_file():
        raise FileNotFoundError(f"Prepared Edge-IIoT train file is missing: {source}")
    if alpha_value == "0.5":
        # Historic alpha=0.5 is a fixed research artifact; no regeneration.
        raise ValueError(
            "alpha=0.5 is the original persisted 'dirichlet' partition. "
            "Its shards must not be regenerated or overwritten."
        )
    target = root / ("dirichlet_alpha_" + alpha_value)
    if target.exists():
        raise FileExistsError(f"Dirichlet partition already exists: {target}")

    frame = pd.read_parquet(source)
    required = {"source_row_id", "target_id"}
    if not required.issubset(frame.columns):
        raise ValueError("Prepared train file lacks source_row_id/target_id")
    if frame.source_row_id.isna().any() or frame.source_row_id.duplicated().any():
        raise ValueError("Prepared train source_row_id must be unique and non-null")
    if frame.target_id.isna().any() or not frame.target_id.isin(range(5)).all():
        raise ValueError("Expected original Edge-IIoT prepared_5 target IDs 0..4")
    if len(frame) < clients:
        raise ValueError("Training rows fewer than requested clients")

    rng = np.random.default_rng(seed)
    labels = frame.target_id.to_numpy()
    membership = None
    # Resample whole allocations rather than silently moving rows between
    # clients: manual repair would violate the intended Dirichlet distribution.
    for _ in range(256):
        assignment = np.full(len(frame), -1, dtype=np.int64)
        for label in sorted(set(labels.tolist())):
            indices = np.flatnonzero(labels == label)
            rng.shuffle(indices)
            proportions = rng.dirichlet(np.repeat(float(alpha_value), clients))
            counts = rng.multinomial(len(indices), proportions)
            start = 0
            for client_id, count in enumerate(counts):
                assignment[indices[start:start + count]] = client_id
                start += count
        if np.all(np.bincount(assignment, minlength=clients) > 0):
            membership = assignment
            break
    if membership is None:
        raise ValueError(
            "Could not generate non-empty shards in 256 deterministic draws; "
            "try a higher alpha or fewer clients."
        )

    # Stage writes in the same filesystem. Never mutate old partitions.
    staging = Path(tempfile.mkdtemp(prefix=".atima-dirichlet-", dir=root))
    try:
        (staging / "clients").mkdir()
        assignment_table = pd.DataFrame({
            "source_row_id": frame.source_row_id,
            "client_id": membership,
        })
        assignment_table.to_parquet(staging / "client_assignment.parquet", index=False)
        per_client = {}
        for client_id in range(clients):
            subset = frame.loc[membership == client_id].copy()
            subset.to_parquet(
                staging / "clients" / f"client_{client_id:02d}.parquet",
                index=False,
            )
            per_client[str(client_id)] = {
                "rows": len(subset),
                "target_counts": {
                    str(label): int(count)
                    for label, count in subset.target_id.value_counts().sort_index().items()
                },
            }

        audit = {
            "format": "atima-dirichlet-shards-v1",
            "alpha": float(alpha_value),
            "alpha_directory": alpha_value,
            "seed": seed,
            "clients": clients,
            "source_train_sha256": _sha256(source),
            "source_rows": len(frame),
            "per_client": per_client,
            "assignment_sha256": _sha256(staging / "client_assignment.parquet"),
        }
        (staging / "partition_manifest.json").write_text(
            json.dumps(audit, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # Confirm complete, disjoint assignment before atomic publish.
        assigned = pd.read_parquet(staging / "client_assignment.parquet")
        if (len(assigned) != len(frame)
                or assigned.source_row_id.duplicated().any()
                or set(assigned.source_row_id) != set(frame.source_row_id)):
            raise RuntimeError("Dirichlet assignment failed source coverage audit")
        if target.exists():
            raise FileExistsError(f"Dirichlet partition already exists: {target}")
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target
