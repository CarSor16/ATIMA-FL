import numpy as np
from atima_fl.core.contracts import Component
from atima_fl.core.vector import krum_scores


def validate(config, params):
    if config.clients <= 2 * params["byzantine_bound"] + 2:
        raise ValueError("Multi-Krum requires n>=2f+3")
    if params["select"] > config.clients - params["byzantine_bound"] - 2:
        raise ValueError("Too many Multi-Krum selections")


def aggregate(matrix, counts, params):
    scores = krum_scores(matrix, params["byzantine_bound"])
    selected = np.argsort(scores, kind="stable")[: params["select"]].tolist()
    return matrix[selected].mean(axis=0), {
        "selected_indices": selected,
        "krum_scores": scores.tolist(),
        "selection_scope": "whole_updates",
        "variant": "one-shot top-m, unweighted mean",
    }


PLUGIN = Component(
    "multi_krum",
    "aggregator",
    "Multi-Krum",
    "One-shot mean of the best m scores.",
    {
        "byzantine_bound": {"type": "integer", "default": 2, "minimum": 0},
        "select": {"type": "integer", "default": 3, "minimum": 1},
    },
    {"validate": validate, "aggregate": aggregate},
    translations={
        "it": {
            "title": "Multi-Krum",
            "description": "Media dei migliori m score in un solo passaggio.",
        }
    },
)
