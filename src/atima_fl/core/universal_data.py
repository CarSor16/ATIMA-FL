"""Dataset-agnostic tabular inspection and reproducible FL preparation.

No pandas/pyarrow imports until an explicit local inspect/prepare request.
No automatic label semantics, unbounded directory walks, or silent row sampling.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from atima_fl.core.numerics import sha256_file

EXTENSIONS = (".csv", ".csv.gz", ".parquet")
_LABEL_NAMES = {"label", "labels", "attack", "attack_type", "attack_cat",
                "category", "class", "target", "outcome", "y"}
_METADATA_NAMES = {"src_ip", "dst_ip", "source_ip", "destination_ip",
                   "timestamp", "time", "flow_id", "id", "source_row_id",
                   "input_fingerprint", "target_id", "fine_label", "session_id",
                   "connection_id", "flowid"}


def source_files(source):
    original = Path(source).expanduser()
    if original.is_symlink():
        raise ValueError("Dataset source symlinks are not accepted")
    root = original.resolve(strict=True)
    if root.is_file():
        if not root.name.lower().endswith(EXTENSIONS):
            raise ValueError("Source must be CSV, CSV.GZ or Parquet")
        paths = [root]
    elif root.is_dir():
        # Intentionally inspect direct children only: never traverse arbitrary trees.
        paths = sorted(p for p in root.iterdir() if p.is_file() and
                       p.name.lower().endswith(EXTENSIONS))
    else:
        raise ValueError("Source must be a local file or directory")
    if not paths or len(paths) > 64:
        raise ValueError("Choose 1..64 CSV/CSV.GZ/Parquet files in one directory")
    if any(p.is_symlink() for p in paths):
        raise ValueError("Dataset source symlinks are not accepted")
    return paths


def _read(path, rows=None):
    import pandas as pd

    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
        return frame.head(rows) if rows is not None else frame
    import csv
    import gzip

    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(8192)
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    return pd.read_csv(path, sep=delimiter, encoding="utf-8-sig",
                       nrows=rows, low_memory=False)


def inspect(source):
    """Suggest labels; ambiguous semantics always require human confirmation."""
    files = source_files(source)
    samples = [_read(p, 5000) for p in files]
    columns = list(samples[0].columns)
    if len(set(columns)) != len(columns) or not columns:
        raise ValueError("Empty or duplicate source columns")
    for sample in samples:
        if list(sample.columns) != columns:
            raise ValueError("Different file schemas in selected directory")
    import pandas as pd

    sample = pd.concat(samples, ignore_index=True)
    candidates = []
    for col in columns:
        name = str(col).lower().strip()
        distinct = int(sample[col].nunique(dropna=True))
        named = name in _LABEL_NAMES
        if named or (2 <= distinct <= 32 and distinct / max(len(sample), 1) <= 0.2
                     and not pd.api.types.is_float_dtype(sample[col])):
            candidates.append({
                "column": str(col), "distinct": distinct,
                "example_values": [str(v) for v in sample[col].dropna().unique()[:16]],
                "reason": "recognized label column name" if named else "low cardinality heuristic",
                "named": named,
            })
    return {
        "path": str(Path(source).expanduser().resolve()), "files": [str(p) for p in files],
        "format": "tabular", "sampled_rows": len(sample), "columns": [str(c) for c in columns],
        "label_candidates": candidates,
        "likely_metadata": [str(c) for c in columns
                            if str(c).lower().strip() in _METADATA_NAMES],
        "requires_confirmation": True,
        "note": "Preview only. Confirm label and benign class; no split or scaling performed.",
    }


def _partition(labels, clients, seed, method):
    rng = np.random.default_rng(seed + (0 if method == "iid" else 31))
    per_client = [[] for _ in range(clients)]
    if method == "iid":
        order = rng.permutation(len(labels))
        for cid, indices in enumerate(np.array_split(order, clients)):
            per_client[cid] = indices.tolist()
    else:
        for label in sorted(set(labels.tolist())):
            order = rng.permutation(np.flatnonzero(labels == label))
            sizes = rng.multinomial(len(order), rng.dirichlet(np.repeat(0.5, clients)))
            for cid, indices in enumerate(np.split(order, np.cumsum(sizes)[:-1])):
                per_client[cid].extend(indices.tolist())
        for empty in [i for i, values in enumerate(per_client) if not values]:
            donor = max(range(clients), key=lambda k: len(per_client[k]))
            if len(per_client[donor]) < 2:
                raise ValueError("Cannot guarantee nonempty client shards")
            per_client[empty].append(per_client[donor].pop())
    return [np.sort(values).astype(np.int64) for values in per_client]


def prepare(source, output, label_column, *, benign_label=None, clients=10,
            seed=2026, exclude_columns=(), max_rows=500000):
    """Write a separate, immutable prepared tree. Fails closed on ambiguous data."""
    import pandas as pd

    if not isinstance(label_column, str) or not label_column:
        raise ValueError("Explicit label_column required")
    if type(clients) is not int or not 2 <= clients <= 1024:
        raise ValueError("clients must be between 2 and 1024")
    if type(seed) is not int or seed < 0:
        raise ValueError("Invalid seed")
    if type(max_rows) is not int or max_rows < 20:
        raise ValueError("Invalid row budget")
    files = source_files(source)
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Prepared output already exists: {destination}")
    if destination.is_relative_to(Path(source).expanduser().resolve()):
        raise ValueError("Prepared output must be outside the input tree")
    columns = None
    chunks = []
    rows = 0
    for path in files:
        if path.suffix.lower() == ".parquet":
            import pyarrow.parquet as parquet

            if parquet.ParquetFile(path).metadata.num_rows > max_rows - rows:
                raise ValueError(f"Source exceeds {max_rows} rows; increase --max-rows")
        frame = _read(path, rows=max_rows - rows + 1)
        if columns is None:
            columns = list(frame.columns)
        if list(frame.columns) != columns:
            raise ValueError("Input files have different schemas")
        rows += len(frame)
        if rows > max_rows:
            raise ValueError(f"Source exceeds {max_rows} rows; increase --max-rows explicitly")
        chunks.append(frame)
    frame = pd.concat(chunks, ignore_index=True)
    if not len(frame) or label_column not in frame:
        raise ValueError("Missing label column or empty dataset")
    if frame[label_column].isna().any():
        raise ValueError("Missing source labels; refuse to invent classes")
    labels = frame[label_column].astype(str).str.strip()
    if (labels == "").any():
        raise ValueError("Empty labels")
    classes = sorted(labels.unique().tolist())
    if len(classes) < 2 or len(classes) > 100:
        raise ValueError("Expected 2..100 distinct classes")
    if benign_label is not None and str(benign_label) not in classes:
        raise ValueError("Declared benign label does not exist")
    exclude = set(exclude_columns)
    if any(col not in columns for col in exclude):
        raise ValueError("Unknown excluded column")
    forbidden = {c for c in columns if str(c).lower().strip() in
                 (_LABEL_NAMES | _METADATA_NAMES)}
    forbidden.update(exclude)
    forbidden.add(label_column)
    feature_columns = [c for c in columns if c not in forbidden]
    if not feature_columns:
        raise ValueError("No eligible features after label/metadata exclusion")

    # Feature-identical records stay in the same split. Contradictory labels
    # for identical inputs are rejected rather than leaked across splits.
    fingerprints = pd.util.hash_pandas_object(
        frame[feature_columns].astype("string").fillna("__MISSING__"), index=False
    ).to_numpy(dtype=np.uint64)
    groups = {}
    for index, (fingerprint, label) in enumerate(zip(fingerprints, labels)):
        group = groups.setdefault(int(fingerprint), {"label": label, "indices": []})
        if group["label"] != label:
            raise ValueError("Conflicting labels for feature-identical source rows")
        group["indices"].append(index)
    rng = np.random.default_rng(seed)
    split_indices = {"train": [], "validation": [], "test": []}
    for label in classes:
        group_keys = [key for key, group in groups.items() if group["label"] == label]
        if len(group_keys) < 3:
            raise ValueError(f"Class {label!r} requires three distinct feature groups")
        rng.shuffle(group_keys)
        count = len(group_keys)
        test = max(1, round(0.15 * count))
        val = max(1, round(0.15 * count))
        if test + val >= count:
            raise ValueError("Too few distinct groups for three splits")
        for split, keys in (
            ("test", group_keys[:test]), ("validation", group_keys[test:test + val]),
            ("train", group_keys[test + val:]),
        ):
            for key in keys:
                split_indices[split].extend(groups[key]["indices"])
    for split in split_indices:
        split_indices[split] = np.array(sorted(split_indices[split]), dtype=np.int64)
    if len(split_indices["train"]) < clients:
        raise ValueError("Training samples fewer than federated clients")
    mapping = {label: index for index, label in enumerate(classes)}

    train = frame.iloc[split_indices["train"]]
    feature_specs = []
    encoded_names = []
    for col in feature_columns:
        series = train[col]
        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
            median = float(numeric.median()) if numeric.notna().any() else 0.0
            cleaned = numeric.fillna(median)
            low, high = float(cleaned.min()), float(cleaned.max())
            feature_specs.append({"name": str(col), "kind": "numeric", "median": median,
                                  "min": low, "max": high})
            encoded_names.append(str(col))
        else:
            categories = sorted(series.fillna("__MISSING__").astype(str).unique().tolist())
            if len(categories) > 32:
                raise ValueError(f"High-cardinality feature {col!r}: exclude it explicitly")
            feature_specs.append({"name": str(col), "kind": "category", "values": categories})
            encoded_names.extend([f"{col}={value}" for value in categories])
    if not 1 <= len(encoded_names) <= 2048:
        raise ValueError("Encoded feature count outside 1..2048")

    def encode(indices):
        selected = frame.iloc[indices]
        values = []
        for spec in feature_specs:
            if spec["kind"] == "numeric":
                numeric = pd.to_numeric(selected[spec["name"]], errors="coerce")
                numeric = numeric.replace([np.inf, -np.inf], np.nan).fillna(spec["median"])
                denominator = spec["max"] - spec["min"]
                value = (numeric.to_numpy(dtype=np.float64) - spec["min"]) / (
                    denominator if denominator > 0 else 1.0
                )
                values.append(value.reshape(-1, 1).astype(np.float32))
            else:
                categorical = selected[spec["name"]].fillna("__MISSING__").astype(str)
                values.append(np.stack([(categorical == item).to_numpy(dtype=np.float32)
                                        for item in spec["values"]], axis=1))
        matrix = np.concatenate(values, axis=1)
        if not np.isfinite(matrix).all():
            raise ValueError("Nonfinite postprocessed features")
        return matrix

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".atima-prepare-", dir=destination.parent))
    try:
        split_frames = {}
        transformed_hashes = set()
        for name, indices in split_indices.items():
            matrix = encode(indices)
            fp = [hashlib.sha256(row.tobytes()).hexdigest() for row in matrix]
            if set(fp) & transformed_hashes:
                raise ValueError("Model feature overlap across train/validation/test")
            transformed_hashes.update(fp)
            subset = pd.DataFrame(matrix, columns=[f"f{i:04d}" for i in range(matrix.shape[1])])
            subset.insert(0, "source_row_id", indices)
            subset.insert(1, "input_fingerprint", fp)
            subset.insert(2, "fine_label", labels.iloc[indices].tolist())
            subset.insert(3, "target_id", [mapping[v] for v in labels.iloc[indices]])
            subset.to_parquet(temp / f"{name}_scaled.parquet", index=False)
            split_frames[name] = subset
        for method in ("iid", "dirichlet"):
            base = temp / method
            (base / "clients").mkdir(parents=True)
            shards = _partition(split_frames["train"].target_id.to_numpy(dtype=np.int64),
                                clients, seed, method)
            assignment = []
            for cid, indices in enumerate(shards):
                subset = split_frames["train"].iloc[indices]
                subset.to_parquet(base / "clients" / f"client_{cid:02d}.parquet", index=False)
                assignment.extend({"source_row_id": int(sid), "client_id": cid}
                                  for sid in subset.source_row_id)
            pd.DataFrame(assignment).to_parquet(base / "client_assignment.parquet", index=False)
        (temp / "feature_schema.json").write_text(json.dumps(
            {"columns": [f"f{i:04d}" for i in range(len(encoded_names))],
             "source_features": feature_columns, "encoded_features": encoded_names},
            indent=2), encoding="utf-8")
        (temp / "label_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        (temp / "preprocessor.json").write_text(json.dumps(
            {"fitted_on": "train", "features": feature_specs}, indent=2), encoding="utf-8")
        (temp / "manifest.json").write_text(json.dumps({
            "format": "atima-universal-tabular-v1", "source_files": [str(p) for p in files],
            "source_hashes": {str(p): sha256_file(p) for p in files},
            "rows": {name: int(len(indices)) for name, indices in split_indices.items()},
            "label_column": label_column, "benign_label": (
                str(benign_label) if benign_label is not None else None),
            "excluded_columns": sorted(str(x) for x in forbidden), "classes": classes,
            "seed": seed, "clients": clients, "partitions": ["iid", "dirichlet"],
            "split_method": "seeded stratified feature-group split; no source feature-group overlap",
            "train_only_preprocessing": True,
        }, indent=2), encoding="utf-8")
        os.replace(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return {
        "path": str(destination), "classes": classes, "num_classes": len(classes),
        "input_dim": len(encoded_names), "benign_label": benign_label,
        "task_options": ["multiclass"] + (["binary"] if benign_label is not None else []),
        "client_count": clients, "rows": {k: len(v) for k, v in split_indices.items()},
    }


def prepared_summary(source):
    """Discover a previously prepared ATIMA tree without reading all training tensors."""
    root = Path(source).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Prepared source must be a directory")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "atima-universal-tabular-v1":
        raise ValueError("Not an ATIMA universal prepared dataset")
    mapping = json.loads((root / "label_mapping.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "feature_schema.json").read_text(encoding="utf-8"))
    if set(mapping.values()) != set(range(len(mapping))) or not schema.get("columns"):
        raise ValueError("Invalid prepared schema")
    return {
        "path": str(root), "classes": sorted(mapping, key=mapping.get),
        "num_classes": len(mapping), "input_dim": len(schema["columns"]),
        "benign_label": manifest.get("benign_label"),
        "task_options": ["multiclass"] + (
            ["binary"] if manifest.get("benign_label") in mapping else []),
        "client_count": manifest["clients"], "rows": manifest["rows"],
    }
