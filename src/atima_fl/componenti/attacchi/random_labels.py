from atima_fl.core.contracts import Component, TrainingBatch
from atima_fl.core.numerics import round_seed
import numpy as np


def prepare(x, y, context):
    p = context.config.parameters("attack")
    rng = np.random.default_rng(round_seed(context.config.seed, context.client, context.round_id))
    indices = np.sort(rng.choice(len(y), int(len(y) * p["poison_rate"]), replace=False))
    # Every selected label changes; avoid accidentally leaving 1/K of them clean.
    offsets = rng.integers(1, context.config.num_classes, size=len(indices))
    y[indices] = (y[indices] + offsets) % context.config.num_classes
    return TrainingBatch(
        x,
        y,
        indices,
        np.empty(0, dtype=np.int64),
        {"attack_applied": bool(len(indices)), "poisoned_labels": len(indices)},
    )


PLUGIN = Component(
    "random_labels",
    "attack",
    "Random labels",
    "Corrupts a fraction of labels without selecting a source-target pair.",
    {"poison_rate": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1}},
    {"prepare": prepare},
    references=("https://arxiv.org/abs/2502.03801",),
    translations={
        "it": {
            "title": "Etichette casuali",
            "description": "Corrompe una quota di label senza scegliere una coppia sorgente-destinazione.",
        }
    },
)
