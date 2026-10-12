"""Clean-label numerical trigger: train target-class examples with altered features only."""
import numpy as np
from atima_fl.core.contracts import Component, TrainingBatch
from atima_fl.core.numerics import round_seed

def validate(config, params):
    ids = params["trigger_indices"]
    if not ids or len(ids) != len(params["trigger_values"]) or len(set(ids)) != len(ids):
        raise ValueError("Trigger coordinates and values must be unique and aligned")
    if any(i < 0 or i >= config.input_dim for i in ids):
        raise ValueError("Trigger index outside feature dimensions")
    if params["target_class"] >= config.num_classes:
        raise ValueError("Clean-label target outside task")

def trigger(x, params):
    result = x.copy()
    result[:, params["trigger_indices"]] = np.asarray(params["trigger_values"], dtype=x.dtype)
    if not np.isfinite(result).all():
        raise ValueError("Non-finite trigger values")
    return result

def prepare(x, y, context):
    p = context.config.parameters("attack")
    candidates = np.flatnonzero(y == p["target_class"])
    rng = np.random.default_rng(round_seed(context.config.seed, context.client, context.round_id))
    indices = np.sort(rng.choice(candidates, int(len(candidates) * p["poison_rate"]), replace=False))
    before = x[indices].copy()
    x[indices] = trigger(x[indices], p)
    changed = bool(not np.array_equal(before, x[indices]))
    return TrainingBatch(x, y, np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
                         {"attack_applied": changed, "triggered_training_rows": int(len(indices)),
                          "scope": "numerical clean-label trigger; packet-level feasibility not verified"})

def evaluate(values, x, y, config, device):
    from atima_fl.engine.models import probabilities
    p = config.parameters("attack")
    eligible = y != p["target_class"]
    if not eligible.any():
        return {"eligible": 0, "asr": None}
    clean = probabilities(values, x[eligible], config, device).argmax(axis=1)
    modified = probabilities(values, trigger(x[eligible], p), config, device).argmax(axis=1)
    return {"eligible": int(eligible.sum()), "target_class": p["target_class"],
            "asr": float(np.mean(modified == p["target_class"])),
            "clean_target_rate": float(np.mean(clean == p["target_class"])),
            "scope": "synthetic numerical trigger, not validated network traffic"}

PLUGIN = Component(
    "clean_label_trigger", "attack", "Clean-label trigger",
    "Adds a numerical trigger to target-class training samples without relabeling or model replacement.",
    {"target_class": {"type": "integer", "default": 0, "minimum": 0},
     "poison_rate": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1},
     "trigger_indices": {"type": "array", "default": [0, 1], "items": {"type": "integer", "minimum": 0}},
     "trigger_values": {"type": "array", "default": [0.9, 0.9], "items": {"type": "number"}}},
    {"validate": validate, "prepare": prepare, "evaluate": evaluate},
    threats=("backdoor", "data_poisoning"),
    limitations="Requires a physically meaningful trigger before claiming a network-level backdoor.",
)
