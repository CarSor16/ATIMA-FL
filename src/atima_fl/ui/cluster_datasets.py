"""Read-only, on-demand university-cluster dataset metadata discovery.

No training, remote file changes, dataset downloads, arbitrary directory walking,
or client-provided remote paths. NF-V2 sources are inspectable only: they do NOT
constitute executable ATIMA dataset adapters.
"""

import json
from pathlib import Path
import re
import subprocess

from atima_fl.core.label_taxonomy import availability, task_catalog
from atima_fl.ui.cluster_results import connection_settings, password_ssh

_DATASET_IDS = ("edge_iiot", "nf_cicids2018", "nf_unsw_nb15", "nf_botiot", "nf_toniot")
_NF_IDS = _DATASET_IDS[1:]
_BAD_CHAR = re.compile(r"[\x00-\x1f\x7f]")
_LIMIT = 256 * 1024


def _remote_path(value):
    if not isinstance(value, str) or not value.startswith("/") or _BAD_CHAR.search(value):
        raise ValueError("Cluster dataset paths must be absolute Linux paths")
    if any(part in {"..", "."} for part in value.split("/")):
        raise ValueError("Cluster dataset paths must not contain . or .. segments")
    if len(value) > 2048:
        raise ValueError("Cluster dataset path too long")
    return value


def configured_dataset_paths(workspace):
    """Default Edge root plus opt-in, explicit NF-V2 raw CSV paths."""
    workspace = Path(workspace)
    path = workspace / "deployment_defaults.json"
    result = {}
    if path.is_file():
        if path.is_symlink() or path.stat().st_size > 16 * 1024:
            raise ValueError("Unsafe deployment_defaults.json")
        content = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(content, dict):
            raise ValueError("Invalid deployment defaults")
        value = content.get("dataset_root")
        if value:
            # Symbolic env: names cannot be resolved on the Windows GUI.
            if isinstance(value, str) and value.startswith("env:"):
                pass
            else:
                result["edge_iiot"] = _remote_path(value)
    optional = workspace / "cluster_dataset_paths.json"
    if optional.is_file():
        if optional.is_symlink() or optional.stat().st_size > 8192:
            raise ValueError("Unsafe cluster_dataset_paths.json")
        data = json.loads(optional.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or set(data) - set(_DATASET_IDS):
            raise ValueError("cluster_dataset_paths.json: unexpected dataset identifiers")
        for key, value in data.items():
            result[key] = _remote_path(value)
    return result


# The Python script only reads explicit paths. Never use find/rglob or remote shells.
_REMOTE_READ = r'''
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

paths = json.loads(PATHS_LITERAL)
out = {}
for kind, value in sorted(paths.items()):
    root = Path(value)
    item = {"path": str(root), "found": False, "source_labels": [],
            "source_complete": False, "rows_scanned": 0, "note": ""}
    if kind == "edge_iiot":
        if not root.is_dir() or root.is_symlink():
            item["note"] = "Prepared Edge-IIoT directory not found"
            out[kind] = item
            continue
        required = ("label_mapping.json", "feature_schema.json", "preprocessor.json",
                    "manifest.json", "train_scaled.parquet",
                    "validation_scaled.parquet", "test_scaled.parquet")
        missing = [name for name in required
                   if not (root / name).is_file() or (root / name).is_symlink()]
        item["found"] = not missing
        item["note"] = "Missing required prepared files: " + ", ".join(missing) if missing else ""
        mapping = root / "label_mapping.json"
        if mapping.is_file() and not mapping.is_symlink() and mapping.stat().st_size < 65536:
            try:
                labels = json.loads(mapping.read_text(encoding="utf-8"))
                if isinstance(labels, dict) and len(labels) <= 100 and all(
                    isinstance(k, str) and type(v) is int for k, v in labels.items()
                ):
                    item["prepared_classes"] = [key for key, _ in
                                                sorted(labels.items(), key=lambda pair: pair[1])]
            except (OSError, ValueError):
                item["note"] += "; malformed label mapping"
        # Read only the original fine-label column; no features leave the cluster.
        if item["found"]:
            try:
                import pandas as pd
                collected = {}
                total = 0
                for split in ("train", "validation", "test"):
                    frame = pd.read_parquet(root / (split + "_scaled.parquet"),
                                            columns=["fine_label"])
                    counts = frame["fine_label"].astype(str).value_counts().to_dict()
                    collected[split] = {str(key): int(n) for key, n in counts.items()}
                    total += sum(collected[split].values())
                    if len(counts) > 100:
                        raise ValueError("Too many original label values")
                item["observed_by_split"] = collected
                item["source_labels"] = sorted(set().union(
                    *(set(row) for row in collected.values())))
                item["rows_scanned"] = total
                item["source_complete"] = True
            except (ImportError, OSError, ValueError, KeyError) as exc:
                item["note"] += "; fine_label unavailable: " + type(exc).__name__
    else:
        if not root.is_file() or root.is_symlink():
            item["note"] = "NF-V2 CSV path not configured or file not found"
            out[kind] = item
            continue
        if root.suffix not in (".csv", ".gz"):
            item["note"] = "Expected .csv or .csv.gz"
            out[kind] = item
            continue
        item["found"] = True
        try:
            opener = gzip.open if root.suffix == ".gz" else open
            # Bound the scan: sample labels, never claim a complete inventory.
            with opener(root, "rt", encoding="utf-8-sig", newline="", errors="replace") as stream:
                reader = csv.DictReader(stream)
                if not {"Attack", "Label"}.issubset(set(reader.fieldnames or [])):
                    item["note"] = "NF-V2 source must have Attack and Label columns"
                else:
                    counts = Counter()
                    for row in reader:
                        if item["rows_scanned"] >= 20000:
                            break
                        counts[str(row["Attack"]).strip()] += 1
                        item["rows_scanned"] += 1
                        if len(counts) > 100:
                            raise ValueError("Too many attack label values")
                    item["source_labels"] = sorted(counts)
                    item["observed_counts_sample"] = dict(counts)
                    item["note"] = "First 20,000 records at most; taxonomy is not exhaustive"
        except (OSError, ValueError, EOFError) as exc:
            item["note"] = "Cannot read source labels: " + type(exc).__name__
    out[kind] = item
print(json.dumps(out, ensure_ascii=False, allow_nan=False))
'''


def _validate_inventory(response, configured):
    if not isinstance(response, dict) or set(response) != set(configured):
        raise ValueError("Unexpected cluster dataset inventory")
    output = {}
    reference = task_catalog()
    for key, item in response.items():
        if not isinstance(item, dict) or item.get("path") != configured[key]:
            raise ValueError("Invalid dataset inventory path")
        if type(item.get("found")) is not bool or type(item.get("source_complete")) is not bool:
            raise ValueError("Invalid dataset inventory status")
        labels = item.get("source_labels")
        if not isinstance(labels, list) or len(labels) > 100 or any(
            not isinstance(label, str) or len(label) > 150 for label in labels
        ):
            raise ValueError("Invalid cluster source labels")
        total = item.get("rows_scanned")
        if type(total) is not int or not 0 <= total <= 100_000_000:
            raise ValueError("Invalid scanned record count")
        note = item.get("note")
        if not isinstance(note, str) or len(note) > 600:
            raise ValueError("Invalid cluster dataset note")
        data = {
            "path": configured[key], "found": item["found"],
            "source_labels": labels, "source_complete": item["source_complete"],
            "rows_scanned": total, "note": note,
            "training_supported": key == "edge_iiot" and item["found"],
        }
        if key == "edge_iiot":
            mapped = item.get("prepared_classes")
            if mapped is not None and (
                not isinstance(mapped, list) or len(mapped) != 5
                or any(not isinstance(x, str) or len(x) > 100 for x in mapped)
            ):
                raise ValueError("Invalid Edge-IIoT label mapping")
            data["prepared_classes"] = mapped
            data["training_supported"] = bool(
                item["found"] and mapped is not None and len(set(mapped)) == 5
            )
            if item["source_complete"]:
                observed = item.get("observed_by_split")
                if not isinstance(observed, dict) or set(observed) != {"train", "validation", "test"}:
                    raise ValueError("Invalid inspected Edge-IIoT splits")
                for counts in observed.values():
                    if not isinstance(counts, dict) or len(counts) > 100 or any(
                        not isinstance(k, str) or type(v) is not int or v < 0
                        for k, v in counts.items()
                    ):
                        raise ValueError("Invalid observed source label counts")
                observed_all = sorted(set().union(*(set(c) for c in observed.values())))
                train_labels = list(observed["train"])
                data["task_availability"] = {
                    task: availability(train_labels, observed_all, task)
                    for task in reference
                }
                data["task_availability"]["prepared_5"]["available"] = data["training_supported"]
                data["observed_by_split"] = observed
        else:
            counts = item.get("observed_counts_sample")
            if counts is not None and (
                not isinstance(counts, dict) or len(counts) > 100 or any(
                    not isinstance(k, str) or type(v) is not int or v < 0
                    for k, v in counts.items()
                )
            ):
                raise ValueError("Invalid sampled NF-V2 counts")
            data["observed_counts_sample"] = counts or {}
            data["training_supported"] = False
        output[key] = data
    return output


def discover_cluster_datasets(workspace, runner=subprocess.run):
    settings = connection_settings(workspace)
    if settings is None:
        raise ValueError("Configure cluster_connection.json in the active workspace")
    paths = configured_dataset_paths(workspace)
    if not paths:
        raise ValueError(
            "No cluster dataset paths configured. Add dataset_root to deployment_defaults.json"
        )
    encoded = json.dumps(paths, ensure_ascii=True)
    script = _REMOTE_READ.replace("PATHS_LITERAL", repr(encoded))
    result = None
    if runner is subprocess.run:
        result = password_ssh(settings, script)
    if result is None:
        command = [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", "-o", "NumberOfPasswordPrompts=0",
            "--", settings["ssh_user"] + "@" + settings["ssh_host"], "python3", "-",
        ]
        try:
            response = runner(command, input=script, text=True,
                              capture_output=True, timeout=55, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("Cluster metadata read failed or timed out") from error
        if response.returncode != 0:
            raise ValueError("Cluster dataset inspection failed; check SSH and remote Python")
        result = response.stdout
    if len(result) > _LIMIT:
        raise ValueError("Cluster dataset inventory exceeds size limit")
    try:
        parsed = json.loads(result)
    except (ValueError, TypeError) as error:
        raise ValueError("Cluster did not return valid dataset JSON") from error
    return {
        "datasets": _validate_inventory(parsed, paths),
        "unconfigured": [key for key in _DATASET_IDS if key not in paths],
        "note": "Read-only SSH inspection; no dataset bytes are downloaded.",
    }
