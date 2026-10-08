"""Seed-level paired bootstrap; rounds/clients never count as replicates."""

import hashlib
import json
from pathlib import Path
import numpy as np
from .storage import atomic_json


def summarize(inputs, output):
    records = [json.loads(Path(path).read_text(encoding="utf-8"))["summary"] for path in inputs]
    if len(records) < 3:
        raise ValueError("At least three independent paired seeds are required")
    if len({row["seed"] for row in records}) != len(records):
        raise ValueError("Duplicate seed: repeated rounds/runs are not independent replicates")
    if len({row["condition_id"] for row in records}) != 1:
        raise ValueError("Statistics require the same experimental condition across seeds")
    if any(row["status"] != "complete" for row in records):
        raise ValueError("Failed runs cannot support efficacy estimates")
    values = np.array([row["delta_test_macro_f1"] for row in records], dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite effects")
    rng = np.random.default_rng(2026)
    means = values[rng.integers(0, len(values), size=(10000, len(values)))].mean(axis=1)
    report = {
        "replicate_unit": "independent paired seed",
        "n_seeds": len(values),
        "seeds": sorted(row["seed"] for row in records),
        "effect": "test macro-F1 attacked minus clean",
        "mean_effect": float(values.mean()),
        "bootstrap_percentile_95_ci": np.quantile(means, [0.025, 0.975]).tolist(),
        "bootstrap_resamples": 10000,
        "bootstrap_seed": 2026,
        "condition_id": records[0]["condition_id"],
        "limitation": "Exploratory interval; three seeds offer limited precision. No multiplicity correction or causal claim.",
        "input_sha256": [hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in inputs],
    }
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=False)
    atomic_json(destination / "statistics.json", report)
    return report


def summarize_defenses(inputs, output):
    """Bootstrap independent seed quartets, with identical protection and protocol."""
    from copy import deepcopy

    records = [json.loads(Path(path).read_text(encoding="utf-8")) for path in inputs]
    if len(records) < 3 or len({r["seed"] for r in records}) != len(records):
        raise ValueError("At least three distinct independent seed quartets are required")
    conditions = []
    for record in records:
        if record["status"] != "complete":
            raise ValueError("Failed runs cannot support efficacy estimates")
        protocol = deepcopy(record["protocol"])
        protocol.pop("seed")
        protocol.pop("initial_weights_sha256")
        conditions.append(
            {
                "protocol": protocol,
                "protection": record["protection"],
                "protection_sources": record["protection_sources"],
                "reference_sources": record["reference_sources"],
            }
        )
    if any(c != conditions[0] for c in conditions[1:]):
        raise ValueError("Defense statistics require the same protocol and protection across seeds")
    rng = np.random.default_rng(2026)
    indices = rng.integers(0, len(records), size=(10000, len(records)))
    estimates = {}
    for key in (
        "attacked_test_macro_f1_recovery",
        "clean_test_macro_f1_change",
        "attack_damage_reduction",
        "aud_reduction",
    ):
        values = np.asarray([r[key] for r in records], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite effects")
        estimates[key] = {
            "mean": float(values.mean()),
            "bootstrap_percentile_95_ci": np.quantile(
                values[indices].mean(axis=1), [0.025, 0.975]
            ).tolist(),
        }
    for key in ("backdoor_asr_reduction", "untriggered_target_rate_change"):
        values = [r.get(key) for r in records]
        if all(v is None for v in values):
            continue
        if any(v is None for v in values) or not np.isfinite(values).all():
            raise ValueError("Mismatched or nonfinite backdoor effects")
        values = np.asarray(values, dtype=float)
        estimates[key] = {
            "mean": float(values.mean()),
            "bootstrap_percentile_95_ci": np.quantile(
                values[indices].mean(axis=1), [0.025, 0.975]
            ).tolist(),
        }
    report = {
        "replicate_unit": "independent seed quartet",
        "n_seeds": len(records),
        "seeds": sorted(r["seed"] for r in records),
        "estimates": estimates,
        "bootstrap_resamples": 10000,
        "bootstrap_seed": 2026,
        "condition": conditions[0],
        "input_sha256": [hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in inputs],
        "limitation": "Exploratory intervals; three seeds offer limited precision. No multiplicity correction.",
    }
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=False)
    atomic_json(destination / "defense_statistics.json", report)
    return report
