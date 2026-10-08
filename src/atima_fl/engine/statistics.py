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
