from atima_fl.core.contracts import Component
from atima_fl.core.numerics import round_seed
import numpy as np


def transform(context):
    from atima_fl.core.vector import flatten, restore

    p = context.config.parameters("attack")
    before = flatten(context.global_arrays)
    delta = flatten(context.local_arrays) - before
    rng = np.random.default_rng(round_seed(context.config.seed, context.client, context.round_id))
    noise = rng.normal(size=len(delta))
    norm = np.linalg.norm(noise)
    # Relative L2 budget: comparable across models with different parameter counts.
    budget = p["relative_l2"] * np.linalg.norm(delta)
    noise *= budget / max(norm, 1e-12)
    sent = delta + noise
    return restore(before + sent, context.global_arrays), {
        "attack_applied": bool(budget),
        "relative_l2": p["relative_l2"],
        "noise_l2": float(budget),
        "variant": "additive isotropic Gaussian direction, normalized to relative L2 budget",
    }


PLUGIN = Component(
    "gaussian_noise",
    "attack",
    "Gaussian delta noise",
    "Adds a Gaussian direction to the delta with a relative L2 budget; this does not corrupt training data.",
    {"relative_l2": {"type": "number", "default": 1.0, "minimum": 0}},
    {"transform": transform},
    references=("https://arxiv.org/abs/2502.03801",),
    threats=("coordinate_outlier", "byzantine_update"),
    translations={
        "it": {
            "title": "Rumore gaussiano nel delta",
            "description": "Aggiunge una direzione gaussiana al delta con budget L2 relativo; non è rumore sui dati.",
        }
    },
)
