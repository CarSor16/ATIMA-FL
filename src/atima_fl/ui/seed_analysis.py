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
    return {"key": hashlib.sha256(raw.encode()).hexdigest(), "reason": None}
