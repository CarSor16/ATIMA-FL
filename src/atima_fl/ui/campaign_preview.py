"""Deterministic, read-only preview of a paired seed campaign.

This module never creates profiles, accesses datasets, or submits jobs.
The user must explicitly export and execute plans in a separate operation.
"""
from atima_fl.core.seed_campaign import SEEDS_0_TO_10, batch_profiles


def paired_seed_preview(config, seeds=SEEDS_0_TO_10):
    """Describe one clean and one attacked profile per seed; legacy API."""
    if config.attack == "none":
        raise ValueError("Select an attack to preview a paired seed campaign")
    if config.minimum_rounds > config.rounds:
        raise ValueError("Minimum rounds exceed the campaign horizon")
    pairs = batch_profiles(config, seeds)
    entries = [{
        "seed": clean.seed,
        "clean_name": clean.name,
        "attack_name": attack.name,
        "paired_clean": attack.paired_clean,
        "execution_order": [clean.name, attack.name],
    } for clean, attack in pairs]
    return {
        "mode": "preview_only",
        "attack": config.attack,
        "seeds": list(seeds),
        "clean_runs": len(entries),
        "attack_runs": len(entries),
        "total_runs": 2 * len(entries),
        "rounds": config.rounds,
        "stopping": "fixed_paired_horizon",
        "warnings": [
            "This preview does not create plans, check cluster resources or launch training.",
            "Actual pairing requires identical audited data, partition shards, runtime and initial state.",
            "Seed differences are not proof of independent dataset captures or devices.",
        ],
        "pairs": entries,
    }
