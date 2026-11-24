"""Validated single-variable sweeps; no dataset access or job execution."""
from dataclasses import replace
import math
from pathlib import PurePosixPath, PureWindowsPath

from atima_fl.core.seed_campaign import batch_profiles

TOP_LEVEL = {"attack_start", "attack_end", "malicious_count", "model", "partition"}
MAX_LEVELS = 12
MAX_RUNS = 300


def sweep_profiles(config, seeds, axis, values):
    """Return ordered groups of clean then attacked profiles and level metadata.

    Attack-only levels reuse one clean per seed to avoid ambiguous clean matches.
    Model and partition levels get separate clean references.
    """
    config.validate()
    if config.attack == "none":
        raise ValueError("Enable an attack before creating a sensitivity sweep")
    if not isinstance(axis, str) or not isinstance(values, list) or not 2 <= len(values) <= MAX_LEVELS:
        raise ValueError("Select an axis and 2..12 distinct levels")
    registry = config.registry()
    resolved = config.resolved()
    numeric = axis.startswith(("attack_params.", "partition_params."))
    if numeric:
        group, key = axis.split(".", 1)
        kind = group.removesuffix("_params")
        component = registry.get(kind, getattr(config, kind))
        schema = component.parameters.get(key, {})
        if schema.get("type") not in {"integer", "number"}:
            raise ValueError("Select a registered numeric parameter")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("Levels must be finite numbers")
        if schema["type"] == "integer" and any(type(v) is not int for v in values):
            raise ValueError("This parameter requires integer levels")
    elif axis in {"model", "partition"}:
        if any(not isinstance(v, str) or not v for v in values):
            raise ValueError("Model and partition levels must be component IDs")
    elif axis in TOP_LEVEL:
        if any(type(v) is not int for v in values):
            raise ValueError("This axis requires integer levels")
    else:
        raise ValueError("Unsupported sweep axis")
    if len(set(values)) != len(values):
        raise ValueError("Duplicate sweep levels")
    shared = axis.startswith("attack_params.") or axis in {"attack_start", "attack_end", "malicious_count"}
    if not isinstance(seeds, (list, tuple)) or not seeds or len(seeds) > 50:
        raise ValueError("Choose 1..50 seeds")
    if len(seeds) * (len(values) + 1 if shared else 2 * len(values)) > MAX_RUNS:
        raise ValueError("Sweep exceeds 300 profiles; split the campaign")
    levels = []
    for index, value in enumerate(values, 1):
        changes = {"name": f"{config.name}_L{index}"}
        if numeric:
            changes[group] = {**resolved[group], key: value}
        elif axis == "malicious_count":
            if not 1 <= value <= config.clients:
                raise ValueError("Malicious count must be between 1 and all clients")
            changes["malicious_clients"] = tuple(range(value))
        elif axis in {"model", "partition"}:
            registry.get(axis, value)
            changes[axis] = value
            changes[axis + "_params"] = resolved[axis + "_params"] if value == getattr(config, axis) else {}
        else:
            if not 1 <= value <= config.rounds:
                raise ValueError("Attack window level must be inside the run horizon")
            changes[axis] = value
        profiles = batch_profiles(replace(config, **changes), seeds)
        levels.append(profiles)
    if not shared:
        return [pair for level in levels for pair in level]
    output = (PureWindowsPath(config.output_root) if PureWindowsPath(config.output_root).drive
              else PurePosixPath(config.output_root))
    groups = []
    for index, seed in enumerate(seeds):
        clean = levels[0][index][0]
        attacks = [replace(level[index][1], paired_clean=str(output / clean.name)) for level in levels]
        for attack in attacks:
            attack.validate()
        groups.append((clean, *attacks))
    return groups
