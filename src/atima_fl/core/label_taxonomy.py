"""Public Edge-IIoTset taxonomy and lossless task projections.

These are *reference labels*, not evidence that a particular prepared dataset
contains every type. Always inspect observed fine_label values before claiming
that a task is available. No data are copied or rewritten here.
"""

FAMILIES = (
    ("Normal", ("Normal",)),
    ("DoS/DDoS", ("DDoS_HTTP", "DDoS_ICMP", "DDoS_TCP", "DDoS_UDP")),
    ("Information Gathering", ("Fingerprinting", "Port_Scanning", "Vulnerability_scanner")),
    ("MITM", ("MITM",)),
    ("Injection", ("SQL_injection", "Uploading", "XSS")),
    ("Malware", ("Backdoor", "Password", "Ransomware")),
)

FINE_CLASSES = tuple(label for _, members in FAMILIES for label in members)
FAMILY_CLASSES = tuple(family for family, _ in FAMILIES)
BINARY_CLASSES = ("Normal", "Attack")

TASK_CLASSES = {
    "binary": BINARY_CLASSES,
    "family_6": FAMILY_CLASSES,
    "fine_15": FINE_CLASSES,
}
TASK_DESCRIPTION = {
    "prepared_5": "Legacy five-class prepared target_id (unchanged)",
    "binary": "Normal vs any attack, from verified fine_label",
    "family_6": "Normal plus five attack families, from verified fine_label",
    "fine_15": "Normal plus fourteen attack types, from verified fine_label",
}

# Case-insensitive exact label lookup: no speculative normalization or guessing.
_FINE_LOOKUP = {name.casefold(): i for i, name in enumerate(FINE_CLASSES)}
_FAMILY_BY_FINE = {
    name.casefold(): family_id
    for family_id, (_, members) in enumerate(FAMILIES)
    for name in members
}


def task_catalog(prepared_classes=None):
    classes = {
        "prepared_5": tuple(prepared_classes) if prepared_classes is not None
        else ("benign", "dos", "infog", "inject", "malware"),
        **TASK_CLASSES,
    }
    return {
        task: {
            "description": TASK_DESCRIPTION[task],
            "num_classes": len(names),
            "class_names": list(names),
        }
        for task, names in classes.items()
    }


def project_labels(fine_labels, task):
    """Convert observed granular labels to integer targets; reject unknown names."""
    import numpy as np

    if task not in TASK_CLASSES:
        raise ValueError(f"Unsupported granular classification task: {task}")
    raw = [str(value).strip() for value in fine_labels]
    normalized = [value.casefold() for value in raw]
    missing = sorted({raw[i] for i, key in enumerate(normalized) if key not in _FINE_LOOKUP})
    if missing:
        raise ValueError(
            f"Cannot derive {task} from fine_label: unknown source labels {missing}. "
            "Recover original labels or select the legacy prepared_5 task."
        )
    if task == "fine_15":
        return np.array([_FINE_LOOKUP[key] for key in normalized], dtype=np.int64)
    if task == "family_6":
        return np.array([_FAMILY_BY_FINE[key] for key in normalized], dtype=np.int64)
    return np.array([int(key != "normal") for key in normalized], dtype=np.int64)


def availability(observed_train, observed_all, task):
    """Explain whether data, not just the published taxonomy, support a task."""
    if task == "prepared_5":
        return {"available": True, "missing_train": [], "unknown_source_labels": []}
    unknown = sorted({value for value in observed_all if value.strip().casefold() not in _FINE_LOOKUP})
    if unknown:
        return {"available": False, "missing_train": [], "unknown_source_labels": unknown}
    projected = project_labels(observed_train, task)
    missing_ids = sorted(set(range(len(TASK_CLASSES[task]))) - set(projected.tolist()))
    return {
        "available": not missing_ids,
        "missing_train": [TASK_CLASSES[task][i] for i in missing_ids],
        "unknown_source_labels": [],
    }
