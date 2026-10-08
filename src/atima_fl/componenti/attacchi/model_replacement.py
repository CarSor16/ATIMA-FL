from atima_fl.core.numerics import round_seed
from atima_fl.core.vector import restore
from atima_fl.engine.attacks import active
from atima_fl.core.contracts import Component, TrainingBatch
from atima_fl.engine.attacks import view
import numpy as np


def trigger(x, config):
    result = x.copy()
    result[:, list(config.trigger_indices)] = config.trigger_values
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite trigger")
    return result


def backdoor_training_data(x, y, config, client, round_id):
    if not active(config, client, round_id) or config.attack != "model_replacement":
        return x, y, np.empty(0, dtype=np.int64)
    candidates = np.flatnonzero(y != config.backdoor_target)
    rng = np.random.default_rng(round_seed(config.seed, client, round_id))
    selected = np.sort(
        rng.choice(candidates, int(len(candidates) * config.poison_rate), replace=False)
    )
    return (
        np.concatenate([x, trigger(x[selected], config)]),
        np.concatenate([y, np.full(len(selected), config.backdoor_target, dtype=np.int64)]),
        selected,
    )


def craft(global_vector, local_vector, counts, config, global_arrays):
    malicious_mass = sum(counts[cid] for cid in config.malicious_clients) / sum(counts.values())
    scale = 1 / malicious_mass
    return restore(global_vector + scale * (local_vector - global_vector), global_arrays), {
        "attack_applied": True,
        "replacement_scale": scale,
    }


def validate(config, params):
    indices, values = params["trigger_indices"], params["trigger_values"]
    if not indices or len(indices) != len(values) or len(set(indices)) != len(indices):
        raise ValueError("Trigger needs distinct coordinates and corresponding values")
    if (
        any(i >= config.input_dim for i in indices)
        or params["backdoor_target"] >= config.num_classes
    ):
        raise ValueError("Trigger coordinates/target outside task dimensions")


def prepare(x, y, context):
    xx, yy, selected = backdoor_training_data(
        x, y, view(context.config), context.client, context.round_id
    )
    return TrainingBatch(
        xx,
        yy,
        np.empty(0, dtype=np.int64),
        selected,
        {"attack_applied": bool(len(selected)), "backdoor_source_indices": selected.tolist()},
    )


def transform(context):
    from atima_fl.core.vector import flatten

    if (
        set(context.counts) != set(range(context.config.clients))
        or min(context.counts.values()) <= 0
    ):
        raise ValueError("Model replacement requires complete positive public sample counts")
    return craft(
        flatten(context.global_arrays),
        flatten(context.local_arrays),
        context.counts,
        view(context.config),
        context.global_arrays,
    )


def evaluate(values, x, y, config, device):
    from atima_fl.engine.models import probabilities

    params = view(config)
    eligible = y != params.backdoor_target
    if not eligible.any():
        return {"non_target_samples": 0, "asr_all_non_target": None}
    clean = probabilities(values, x[eligible], config, device)
    attacked = probabilities(values, trigger(x[eligible], params), config, device)
    return {
        "target": params.backdoor_target,
        "non_target_samples": int(eligible.sum()),
        "asr_all_non_target": float((attacked.argmax(axis=1) == params.backdoor_target).mean()),
        "clean_target_rate_on_non_target": float(
            (clean.argmax(axis=1) == params.backdoor_target).mean()
        ),
        "scope": "numerical trigger; physical packet plausibility and persistence not established",
    }


PLUGIN = Component(
    "model_replacement",
    "attack",
    "ModelReplacement / Backdoor",
    "Numerical trigger and train-and-scale; exact replacement depends on benign deltas.",
    {
        "poison_rate": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1},
        "trigger_indices": {
            "type": "array",
            "default": [0, 1],
            "items": {"type": "integer", "minimum": 0},
        },
        "trigger_values": {"type": "array", "default": [0.9, 0.9], "items": {"type": "number"}},
        "backdoor_target": {"type": "integer", "default": 0, "minimum": 0},
    },
    {"validate": validate, "prepare": prepare, "transform": transform, "evaluate": evaluate},
    references=("https://proceedings.mlr.press/v108/bagdasaryan20a.html",),
    threats=("backdoor", "large_norm", "byzantine_update"),
    translations={
        "it": {
            "title": "ModelReplacement / Backdoor",
            "description": "Trigger numerico e train-and-scale; la sostituzione esatta dipende dai delta benigni.",
        }
    },
)
