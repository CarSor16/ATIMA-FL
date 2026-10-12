"""Distribution poisoning: remove a target class from compromised clients' local training."""
import numpy as np
from atima_fl.core.contracts import Component, TrainingBatch
from atima_fl.core.numerics import round_seed

def validate(config, params):
    if params["target_class"] >= config.num_classes:
        raise ValueError("Class withholding target outside task")
    if not 0 < params["remove_fraction"] <= 1:
        raise ValueError("Removal fraction must be in (0,1]")

def prepare(x, y, context):
    p = context.config.parameters("attack")
    candidates = np.flatnonzero(y == p["target_class"])
    rng = np.random.default_rng(round_seed(context.config.seed, context.client, context.round_id))
    removed = np.sort(rng.choice(candidates, int(len(candidates) * p["remove_fraction"]), replace=False))
    keep = np.ones(len(y), dtype=bool)
    keep[removed] = False
    if not keep.any():
        raise ValueError("Class withholding would leave an empty client shard")
    return TrainingBatch(x[keep].copy(), y[keep].copy(), np.empty(0, dtype=np.int64),
                         np.empty(0, dtype=np.int64),
                         {"attack_applied": bool(len(removed)), "withheld_class": p["target_class"],
                          "withheld_samples": int(len(removed)),
                          "scope": "local data distribution; aggregation uses original declared mass"})

PLUGIN = Component(
    "class_withholding", "attack", "Class withholding",
    "Drops selected-class examples from compromised client training; labels remain unchanged.",
    {"target_class": {"type": "integer", "default": 1, "minimum": 0},
     "remove_fraction": {"type": "number", "default": 0.7, "minimum": 0.000001, "maximum": 1.0}},
    {"validate": validate, "prepare": prepare},
    threats=("data_poisoning", "class_imbalance"),
    limitations="Class suppression may be indistinguishable from genuine non-IID scarcity without trusted distribution audits.",
)
