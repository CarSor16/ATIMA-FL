"""Scientific organization of *implemented* attack plugins.

Category labels are orthogonal to threat-model capabilities and do not claim
that an attack has been empirically effective or validated on a given dataset.
Proposed attacks belong in the roadmap, never in Registry.catalog().
"""

ATTACK_GROUPS = {
    "data_poisoning": (
        "label_flip", "random_labels", "feature_noise", "class_withholding",
    ),
    "byzantine_aggregation_disruption": (
        "update_scaling", "sign_flip", "gaussian_noise", "alie", "ipm", "fang",
    ),
    "targeted_model_poisoning": ("local_class_gradient",),
    "backdoor": ("clean_label_trigger", "model_replacement"),
    "protocol_identity": ("sample_weight_hijack", "sybil_collusion", "stale_replay"),
    "free_riding_availability": ("free_rider",),
}

ATTACK_REFERENCES = {
    "data_poisoning": (
        "https://arxiv.org/abs/2306.03397",
        "https://www.mdpi.com/2624-800X/6/4/133",
    ),
    "byzantine_aggregation_disruption": (
        "https://arxiv.org/abs/2306.03397",
        "https://doi.org/10.1109/TPAMI.2023.3322785",
    ),
    "targeted_model_poisoning": (
        "https://arxiv.org/abs/2306.03397",
    ),
    "backdoor": ("https://arxiv.org/abs/2303.02213",),
    "protocol_identity": (
        "https://doi.org/10.1080/08839514.2024.2410504",
    ),
    "free_riding_availability": (
        "https://doi.org/10.1080/08839514.2024.2410504",
    ),
}

_ATTACK_TO_GROUP = {
    attack_id: group
    for group, members in ATTACK_GROUPS.items()
    for attack_id in members
}


def classify_attack(attack_id):
    """Return optional taxonomy metadata without affecting attack execution."""
    group = _ATTACK_TO_GROUP.get(attack_id)
    return {
        "category": group or "uncategorized",
        "implementation_status": "implemented",
        "survey_references": list(ATTACK_REFERENCES.get(group, ())),
    }


def validate_taxonomy(available_attack_ids):
    """Fail on missing or multiply declared built-in attack IDs."""
    listed = [identifier for members in ATTACK_GROUPS.values() for identifier in members]
    if len(listed) != len(set(listed)):
        raise ValueError("Attack taxonomy contains duplicate identifiers")
    missing = set(available_attack_ids) - set(listed)
    stale = set(listed) - set(available_attack_ids)
    if missing or stale:
        raise ValueError(
            f"Attack taxonomy mismatch: unclassified={sorted(missing)}, stale={sorted(stale)}"
        )
