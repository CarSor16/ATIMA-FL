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
    "Selects the update with the lowest score; requires n≥2f+3.",
    {"byzantine_bound": {"type": "integer", "default": 2, "minimum": 0}},
    {"validate": validate, "aggregate": aggregate},
    mitigates=("byzantine_update", "coordinate_outlier"),
    limitations="Assumptions apply within each aggregation group. Non-IID honest updates, ALIE and adaptive Fang attacks can undermine robustness; validate the Byzantine bound locally.",
    references=(
        "https://proceedings.neurips.cc/paper/2017/hash/f4b9ec30ad9f68f89b29639786cb62ef-Abstract.html",
    ),
    translations={
        "it": {
            "limitations": "Le ipotesi valgono in ogni gruppo di aggregazione. Update onesti non-IID, ALIE e Fang adattivo possono compromettere la robustezza; verificare localmente il limite bizantino.",
            "title": "Krum",
            "description": "Seleziona l’update con score minimo; requisito n≥2f+3.",
        }
    },
)
