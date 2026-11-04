"""Deterministic, read-only preview of a paired seed campaign.

This module never creates profiles, accesses datasets, or submits jobs.
The user must explicitly export and execute plans in a separate operation.
"""
from dataclasses import replace
from pathlib import PurePosixPath

SEEDS_0_TO_10 = tuple(range(11))


def paired_seed_preview(config, seeds=SEEDS_0_TO_10):
    """Describe one clean and one attacked profile per independent seed."""
    config.validate()
    if config.attack == "none":
        raise ValueError("Select an attack to preview a paired seed campaign")
    if config.paired_clean:
        raise ValueError("Remove the existing paired_clean path before planning a new campaign")
    if type(seeds) not in (tuple, list) or not seeds or len(seeds) > 50:
        raise ValueError("Campaign seeds must be a list of 1..50 integers")
    if any(type(seed) is not int or not 0 <= seed <= 2**32 - 1 for seed in seeds):
        raise ValueError("Campaign seeds must be non-negative 32-bit integers")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Duplicate campaign seeds")
    # A fixed horizon prevents post-hoc differences from clean early stopping.
    if config.minimum_rounds > config.rounds:
        raise ValueError("Minimum rounds exceed the campaign horizon")
    output = PurePosixPath(config.output_root)
    entries = []
    for seed in seeds:
        stem = f"{config.name}_Seed{seed}"
        clean = replace(
            config, name=stem + "_Clean", seed=seed, attack="none",
            attack_params={}, malicious_clients=(), paired_clean="",
            minimum_rounds=config.rounds, paired_rounds=config.rounds,
        )
        attack = replace(
            config, name=stem + "_Attack", seed=seed,
            minimum_rounds=config.rounds, paired_rounds=config.rounds,
            paired_clean=str(output / clean.name),
        )
        clean.validate()
        attack.validate()
        entries.append({
            "seed": seed,
            "clean_name": clean.name,
            "attack_name": attack.name,
            "paired_clean": attack.paired_clean,
            "execution_order": [clean.name, attack.name],
        })
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
