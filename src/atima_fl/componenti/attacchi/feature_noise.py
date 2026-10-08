from atima_fl.core.contracts import Component, TrainingBatch
from atima_fl.core.numerics import round_seed
import numpy as np


def validate(config, params):
    if not params["indices"] or len(set(params["indices"])) != len(params["indices"]):
        raise ValueError("Feature perturbation needs distinct selected coordinates")
    if any(i < 0 or i >= config.input_dim for i in params["indices"]):
        raise ValueError("Perturbed coordinate outside input dimensions")
    if params["clip_min"] >= params["clip_max"]:
        raise ValueError("Feature clip bounds must be increasing")


def prepare(x, y, context):
    p = context.config.parameters("attack")
    rng = np.random.default_rng(round_seed(context.config.seed, context.client, context.round_id))
    rows = np.sort(rng.choice(len(y), int(len(y) * p["poison_rate"]), replace=False))
    coordinates = np.ix_(rows, p["indices"])
    values = x[coordinates].astype(np.float64)
    original_values = x[coordinates].copy()
    values += rng.normal(0, p["sigma"], size=values.shape)
    x[coordinates] = np.clip(values, p["clip_min"], p["clip_max"]).astype(x.dtype)
    return TrainingBatch(
        x,
        y,
        np.empty(0, dtype=np.int64),
        np.empty(0, dtype=np.int64),
        {
            "attack_applied": not np.array_equal(x[coordinates], original_values),
            "changed_input_indices": rows.tolist(),
            "feature_indices": p["indices"],
            "input_sigma": p["sigma"],
            "scope": "numerical feature poisoning; packet feasibility/padding invariants not established",
        },
    )


PLUGIN = Component(
    "feature_noise",
    "attack",
    "Perturbazione delle feature",
    "Corrompe feature selezionate dei dati locali, conservando le label. Variante numerica, non attacco di rete fisicamente validato.",
    {
        "poison_rate": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1},
        "indices": {"type": "array", "default": [0, 1], "items": {"type": "integer", "minimum": 0}},
        "sigma": {"type": "number", "default": 0.1, "minimum": 0},
        "clip_min": {"type": "number", "default": 0.0},
        "clip_max": {"type": "number", "default": 1.0},
    },
    {"validate": validate, "prepare": prepare},
    references=("https://arxiv.org/abs/2403.02983",),
)
