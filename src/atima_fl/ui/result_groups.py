"""Descriptive grouping metadata for the ATIMA Studio Results explorer.

Grouping is not a scientific comparison: only separately verified clean/attack
pairs permit causal-looking paired summaries. Never infer dates from file mtime.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from atima_fl.core.attack_taxonomy import classify_attack

_DATE_PATTERN = re.compile(r"(?<![0-9])(20[0-9]{2}-[01][0-9]-[0-3][0-9])(?![0-9])")
_FAMILY_NAMES = {
    "data_poisoning": "Data poisoning",
    "byzantine_aggregation_disruption": "Byzantine / aggregation disruption",
    "targeted_model_poisoning": "Targeted model poisoning",
    "backdoor": "Backdoor",
    "protocol_identity": "Protocol / identity manipulation",
    "free_riding_availability": "Free-riding / availability",
    "uncategorized": "Other / unclassified",
}


def _campaign_date(directory_name):
    # Historical experiment directories contain campaign dates, not a manifest
    # execution timestamp. Keep unknown when the name does not contain one.
    for match in _DATE_PATTERN.finditer(str(directory_name)):
        try:
            date.fromisoformat(match.group(1))
        except ValueError:
            continue
        return match.group(1)
    return None


def _partition_label(config):
    identifier = str(config.get("partition") or "").lower()
    if identifier == "iid":
        return "IID", "IID"
    if identifier == "dirichlet":
        params = config.get("partition_params") or {}
        alpha = params.get("alpha") if isinstance(params, dict) else None
        try:
            value = Decimal(str(alpha))
            if value.is_finite() and value > 0:
                return "Non-IID", "Dirichlet alpha=" + format(value.normalize(), "f")
        except (InvalidOperation, TypeError, ValueError):
            pass
        return "Non-IID", "Dirichlet alpha=unknown"
    if identifier in {"non_iid", "non-iid", "noniid"}:
        return "Non-IID", "Non-IID (unspecified)"
    return "Unknown", identifier or "Unknown"


def result_group(manifest, directory_name):
    """Create read-only descriptive labels, with unknowns kept explicit."""
    config = manifest.get("config") or {}
    if not isinstance(config, dict):
        config = {}
    attack = str(config.get("attack") or "unknown").strip().lower()
    category = "clean_baseline" if attack == "none" else classify_attack(attack)["category"]
    family = "Clean baseline" if category == "clean_baseline" else _FAMILY_NAMES.get(category, _FAMILY_NAMES["uncategorized"])
    distribution, partition_detail = _partition_label(config)
    params = config.get("dataset_params") or {}
    audit = manifest.get("dataset_audit") or {}
    task = (params.get("task") if isinstance(params, dict) else None) or (
        audit.get("task") if isinstance(audit, dict) else None
    )
    return {
        "family": family,
        "category": category,
        "attack": attack,
        "campaign_date": _campaign_date(directory_name),
        "date_source": "directory_name" if _campaign_date(directory_name) else "unknown",
        "distribution": distribution,
        "partition_detail": partition_detail,
        "model": str(config.get("model") or "Unknown"),
        "dataset": str(config.get("dataset") or "Unknown"),
        "task": str(task or "Unknown"),
        "seed": config.get("seed"),
    }
