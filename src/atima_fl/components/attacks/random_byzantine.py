"""Deterministic untargeted Byzantine baseline using a bounded random direction."""

import numpy as np

from atima_fl.core.contracts import Component
from atima_fl.core.numerics import round_seed
from atima_fl.core.vector import flatten, restore


def transform(context):
    params = context.config.parameters("attack")
    global_vector = flatten(context.global_arrays)
    local_delta = flatten(context.local_arrays) - global_vector
    reference = float(np.linalg.norm(local_delta))
    if reference == 0.0:
        return [a.copy() for a in context.local_arrays], {
            "attack_applied": False,
            "reason": "zero reference delta",
            "relative_l2": params["relative_l2"],
        }
    rng = np.random.default_rng(
        round_seed(context.config.seed, context.client, context.round_id)
    )
    direction = rng.normal(size=len(local_delta))
    norm = float(np.linalg.norm(direction))
    if norm == 0.0 or not np.isfinite(norm):
        raise ValueError("Cannot construct a finite random Byzantine direction")
    poisoned = global_vector + direction * (params["relative_l2"] * reference / norm)
    return restore(poisoned, context.global_arrays), {
        "attack_applied": True,
        "relative_l2": params["relative_l2"],
        "submitted_delta_l2": params["relative_l2"] * reference,
        "objective": "untargeted arbitrary update baseline; degradation not guaranteed",
    }


PLUGIN = Component(
    "random_byzantine",
    "attack",
    "Random Byzantine",
    "Replaces the local-model delta with a deterministic random direction of declared relative L2 norm.",
    {"relative_l2": {"type": "number", "default": 5.0, "minimum": 0.000001}},
    {"transform": transform},
    threats=("byzantine_update",),
    limitations="Random-direction baseline, not a paper-specific optimized poisoning attack.",
    translations={"it": {
        "title": "Byzantine casuale",
        "description": "Sostituisce il delta con una direzione casuale deterministica e norma L2 controllata.",
    }},
)
