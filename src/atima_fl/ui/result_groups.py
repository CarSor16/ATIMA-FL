"""Read-only classification of imported experiments for the Results explorer.

Grouping is presentational. Never infer scientific comparability from a group.
Only the existing verified clean/attack pairing mechanism can authorize deltas.
"""

import re

ATTACK_FAMILIES = {
    "none": "Clean baseline",
    "label_flip": "Data poisoning",
    "labelflip": "Data poisoning",
    "random_labels": "Data poisoning",
    "feature_noise": "Data poisoning",
    "class_withholding": "Data poisoning",
    "clean_label_trigger": "Backdoor / trigger",
    "model_replacement": "Backdoor / trigger",
    "backdoor": "Backdoor / trigger",
    "alie": "Model poisoning",
    "ipm": "Model poisoning",
    "fang": "Model poisoning",
    "sign_flip": "Model poisoning",
    "gaussian_update_noise": "Model poisoning",
    "update_scaling": "Model poisoning",
    "local_class_gradient": "Model poisoning",
    "free_rider": "Protocol / contribution manipulation",
    "stale_replay": "Protocol / contribution manipulation",
    "sybil_collusion": "Protocol / contribution manipulation",
    "sample_weight_hijack": "Protocol / contribution manipulation",
}

_DATE = re.compile(r"(?<![0-9])(20[0-9]{2}-[01][0-9]-[0-3][0-9])(?![0-9])")


def classify_run(manifest, directory_name):
    """Return descriptive grouping tags; unknown metadata remains unknown."""
    config = manifest.get("config") or {}
    attack = str(config.get("attack") or "unknown").strip().lower()
    partition = str(config.get("partition") or "").strip().lower()
    if partition == "iid":
        distribution = "IID"
    elif partition in {"dirichlet", "non_iid", "non-iid", "noniid"}:
        distribution = "Non-IID"
    else:
        distribution = "Unknown"

    # Campaign directory names carry dates in historical imports. Do not
    # reinterpret filesystem mtimes as the experiment's execution date.
    name = str(directory_name)
    match = _DATE.search(name)
    date = match.group(1) if match else "Unknown"
    dataset_params = config.get("dataset_params") or {}
    task = dataset_params.get("task") or (manifest.get("dataset_audit") or {}).get("task")
    return {
        "attack": attack,
        "family": ATTACK_FAMILIES.get(attack, "Other / unclassified"),
        "date": date,
        "distribution": distribution,
        "partition": partition or "unknown",
        "model": str(config.get("model") or "unknown"),
        "dataset": str(config.get("dataset") or "unknown"),
        "task": str(task or "unknown"),
        "seed": config.get("seed"),
    }
