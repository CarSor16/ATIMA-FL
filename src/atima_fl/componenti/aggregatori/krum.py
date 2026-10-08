import numpy as np
from atima_fl.core.contracts import Component
from atima_fl.core.vector import krum_scores


def validate(config, params):
    if config.clients <= 2 * params["byzantine_bound"] + 2:
        raise ValueError("Krum requires n>=2f+3")


def aggregate(matrix, counts, params):
    scores = krum_scores(matrix, params["byzantine_bound"])
    index = int(np.argmin(scores))
    return matrix[index].copy(), {
        "selected_indices": [index],
        "krum_scores": scores.tolist(),
        "selection_scope": "whole_update",
    }


PLUGIN = Component(
    "krum",
    "aggregator",
    "Krum",
    "Seleziona l’update con score minimo; requisito n≥2f+3.",
    {"byzantine_bound": {"type": "integer", "default": 2, "minimum": 0}},
    {"validate": validate, "aggregate": aggregate},
)
