"""Shared campaign profile construction, independent of Studio and Runtime."""
from dataclasses import replace
from pathlib import PurePosixPath, PureWindowsPath
import re

_RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
SEEDS_0_TO_10 = tuple(range(11))


def batch_profiles(config, seeds=SEEDS_0_TO_10):
    """Validate all profiles before exporting anything; clean-only or paired."""
    config.validate()
    if config.paired_clean:
        raise ValueError("Remove the existing paired_clean path before planning a new campaign")
    if type(seeds) not in (tuple, list) or not seeds or len(seeds) > 50:
        raise ValueError("Campaign seeds must be a list of 1..50 integers")
    if any(type(seed) is not int or not 0 <= seed <= 2**32 - 1 for seed in seeds):
        raise ValueError("Campaign seeds must be non-negative 32-bit integers")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Duplicate campaign seeds")
    output = (PureWindowsPath(config.output_root) if PureWindowsPath(config.output_root).drive
              else PurePosixPath(config.output_root))
    pairs = []
    for seed in seeds:
        stem = f"{config.name}_Seed{seed}"
        clean = replace(
            config, name=stem + "_Clean", seed=seed, attack="none",
            attack_params={}, malicious_clients=(), paired_clean="",
            minimum_rounds=config.rounds, paired_rounds=config.rounds,
        )
        attack = None if config.attack == "none" else replace(
            config, name=stem + "_Attack", seed=seed,
            minimum_rounds=config.rounds, paired_rounds=config.rounds,
            paired_clean=str(output / clean.name),
        )
        for profile in (clean, attack):
            if profile is None:
                continue
            if not _RUN_NAME.fullmatch(profile.name):
                raise ValueError("Generated run names must be ASCII-safe and at most 120 characters")
            profile.validate()
        pairs.append((clean, attack))
    return pairs

