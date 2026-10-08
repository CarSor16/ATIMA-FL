from atima_fl.core.contracts import Component, TrainingBatch
from atima_fl.core.numerics import round_seed
import numpy as np


def validate(config, params):
    if params["source_class"] == params["destination_class"]:
        raise ValueError("Source and destination must differ")
    if max(params["source_class"], params["destination_class"]) >= config.num_classes:
        raise ValueError("Targeted class outside task mapping")


def prepare(x, y, context):
    p = context.config.parameters("attack")
    candidates = np.flatnonzero(y == p["source_class"])
    rng = np.random.default_rng(round_seed(context.config.seed, context.client, context.round_id))
    indices = np.sort(
        rng.choice(candidates, int(len(candidates) * p["poison_rate"]), replace=False)
    )
    y[indices] = p["destination_class"]
    return TrainingBatch(
        x,
        y,
        indices,
        np.empty(0, dtype=np.int64),
        {"attack_applied": bool(len(indices)), "poisoned_labels": len(indices)},
    )


PLUGIN = Component(
    "label_flip",
    "attack",
    "Targeted LabelFlip",
    "Relabels one source class as a chosen target class.",
    {
        "source_class": {"type": "integer", "default": 1, "minimum": 0},
        "destination_class": {"type": "integer", "default": 0, "minimum": 0},
        "poison_rate": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1},
    },
    {"validate": validate, "prepare": prepare},
    references=("https://arxiv.org/abs/2207.01982",),
    translations={
        "it": {
            "title": "LabelFlip mirato",
            "description": "Una classe sorgente viene rietichettata verso una destinazione.",
        }
    },
)
