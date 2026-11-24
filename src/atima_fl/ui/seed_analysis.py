"""Metadata-only equivalence for descriptive, fixed-partition seed summaries.

The existing trajectory-based statistical CLI remains authoritative for verified
paired inference. No training dependencies are required in Studio.
"""
import hashlib
import json

_GLOBAL_HASHES = (
    "train", "validation", "test", "feature_schema.json",
    "label_mapping.json", "preprocessor.json", "assignment",
)
_REQUIRED_CONFIG = (
    "attack", "attack_params", "malicious_clients", "clients", "servers",
    "dataset", "dataset_params", "partition", "partition_params", "model",
    "model_params", "rounds", "local_epochs", "aggregation", "aggregation_params",
    "defenses", "optimizer", "optimizer_params", "loss", "loss_params",
    "batch_size", "learning_rate", "attack_start", "attack_end",
)
_IGNORED = {"name", "seed", "dataset_root", "output_root", "paired_clean", "plugin_directory"}


def seed_condition(manifest):
    """Return an opaque cohort key, or an actionable exclusion reason.

    Only names, seed and paths vary. Exact audited shards, runtime, software,
    malicious IDs, training method, evaluation scope and attack parameters must
    match. Older manifests lacking proof remain individually viewable.
    """
    config = manifest.get("config")
    audit = manifest.get("dataset_audit")
    if manifest.get("status") != "complete":
        return {"key": None, "reason": "Incomplete run"}
    if not isinstance(config, dict) or any(key not in config for key in _REQUIRED_CONFIG):
        return {"key": None, "reason": "Incomplete experiment configuration"}
    seed, clients, rounds = config.get("seed"), config.get("clients"), manifest.get("last_valid_round")
    if type(seed) is not int or seed < 0:
        return {"key": None, "reason": "Missing or invalid seed"}
    if type(clients) is not int or not 1 <= clients <= 10000:
        return {"key": None, "reason": "Missing or invalid client count"}
    if type(rounds) is not int or rounds <= 0 or type(config["rounds"]) is not int or rounds > config["rounds"]:
        return {"key": None, "reason": "Missing or invalid completed round count"}
    malicious = config["malicious_clients"]
    if (not isinstance(malicious, (list, tuple))
            or any(type(cid) is not int or not 0 <= cid < clients for cid in malicious)
            or len(set(malicious)) != len(malicious)
            or (config["attack"] != "none" and not malicious)):
        return {"key": None, "reason": "Missing or invalid malicious-client IDs"}
    if not isinstance(audit, dict) or not audit.get("task"):
        return {"key": None, "reason": "Missing dataset audit or task"}
    hashes, classes = audit.get("hashes"), audit.get("classes")
    required = (*_GLOBAL_HASHES, *(f"client_{cid}" for cid in range(clients)))
    if not isinstance(hashes, dict) or any(
        not isinstance(hashes.get(key), str) or not hashes[key] for key in required
    ):
        return {"key": None, "reason": "Missing audited split, assignment or shard hashes"}
    if (not isinstance(classes, list) or len(classes) < 2
            or any(not isinstance(name, str) for name in classes)
            or len(set(classes)) != len(classes)):
        return {"key": None, "reason": "Missing or invalid audited class order"}
    source, runtime = manifest.get("source_identity"), manifest.get("runtime")
    if not isinstance(source, dict) or not source or not isinstance(runtime, dict) or not runtime:
        return {"key": None, "reason": "Missing software or runtime identity"}
    params = config.get("dataset_params")
    if not isinstance(params, dict) or (params.get("task") and params["task"] != audit["task"]):
        return {"key": None, "reason": "Inconsistent task metadata"}
    condition = {
        "config": {k: v for k, v in config.items() if k not in _IGNORED},
        "dataset_hashes": hashes,
        "task": audit["task"],
        "classes": classes,
        "source": source,
        "runtime": runtime,
        "attack_source": manifest.get("attack_source"),
        "round": rounds,
    }
    try:
        raw = json.dumps(condition, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return {"key": None, "reason": "Invalid protocol metadata"}
    # Preserve exact provenance for strict cohorts and portable study evidence.
    # A descriptive protocol cohort may span prepared shard and runtime versions.
    protocol = {
        "config": {k: v for k, v in condition["config"].items()
                   if k not in {"cpu_budget", "client_cpus", "client_gpu_fraction", "compute_device"}},
        "dataset_hashes": {k: hashes[k] for k in _GLOBAL_HASHES if k != "assignment"},
        "task": condition["task"],
        "classes": classes,
        "round": rounds,
    }
    protocol_raw = json.dumps(protocol, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return {
        "key": hashlib.sha256(raw.encode()).hexdigest(),
        "protocol_key": hashlib.sha256(protocol_raw.encode()).hexdigest(),
        "reason": None,
    }


def sensitivity_conditions(manifest, eligibility):
    """Derive per-axis comparison families from complete audited manifests.

    Model/partition comparisons are descriptive condition contrasts, not
    paired experiments between levels. Each level still needs its own clean.
    """
    if not eligibility.get("key"):
        return []
    config = manifest["config"]
    if config["attack"] == "none":
        return []
    from copy import deepcopy
    import math

    base = {
        "config": {k: v for k, v in config.items() if k not in _IGNORED},
        "dataset_hashes": manifest["dataset_audit"]["hashes"],
        "task": manifest["dataset_audit"]["task"],
        "classes": manifest["dataset_audit"]["classes"],
        "source": manifest["source_identity"],
        "runtime": manifest["runtime"],
        "attack_source": manifest.get("attack_source"),
        "round": manifest["last_valid_round"],
    }
    axes = []
    for field in ("attack_params", "partition_params"):
        for key, value in config[field].items():
            if type(value) in (int, float) and math.isfinite(value):
                axes.append((f"{field}.{key}", value))
    for field in ("model", "partition", "attack_start", "attack_end"):
        axes.append((field, config[field]))
    ids = config["malicious_clients"]
    if sorted(ids) == list(range(len(ids))):
        axes.append(("malicious_count", len(ids)))
    result = []
    for axis, value in axes:
        condition = deepcopy(base)
        cfg = condition["config"]
        if "." in axis:
            group, key = axis.split(".", 1)
            cfg[group].pop(key)
        elif axis == "malicious_count":
            cfg.pop("malicious_clients")
        else:
            cfg.pop(axis)
            if axis in {"model", "partition"}:
                cfg.pop(axis + "_params")
                # The selected component is the deliberately varied variable.
                # Keep every other shared source fingerprint unchanged.
                condition["source"].pop(f"component/{axis}/{value}", None)
        descriptive = axis == "model" or axis == "partition" or axis.startswith("partition_params.")
        if axis == "partition" or axis.startswith("partition_params."):
            # Global train/validation/test, schema and labels remain identical.
            # Shard/assignment identity is deliberately allowed to change.
            condition["dataset_hashes"] = {
                k: v for k, v in condition["dataset_hashes"].items()
                if k in _GLOBAL_HASHES and k != "assignment"
            }
        raw = json.dumps([axis, condition], sort_keys=True, allow_nan=False, separators=(",", ":"))
        result.append({"axis": axis, "value": value,
                       "key": hashlib.sha256(raw.encode()).hexdigest(),
                       "descriptive": descriptive})
    return result
