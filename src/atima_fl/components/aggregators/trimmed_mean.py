import numpy as np
from atima_fl.core.contracts import Component


def validate(config, params):
    if 2 * params["trim_count"] >= config.clients:
        raise ValueError("Trimmed mean requires n>2k")


def aggregate(matrix, counts, params):
    k = params["trim_count"]
    if 2 * k >= len(matrix):
        raise ValueError("Too many trimmed clients")
    result = np.sort(matrix, axis=0)[k : len(matrix) - k].mean(axis=0)
    return result, {
        "selected_indices": None,
        "selection_scope": "coordinatewise_trimmed_mean",
        "trim_count": k,
    }


PLUGIN = Component(
    "trimmed_mean",
    "aggregator",
    "Trimmed mean",
    "Removes k extremes from each side of every coordinate.",
    {"trim_count": {"type": "integer", "default": 2, "minimum": 0}},
    {"validate": validate, "aggregate": aggregate},
    mitigates=("byzantine_update", "coordinate_outlier"),
    limitations="Assumptions apply within each aggregation group. Non-IID honest updates, ALIE and adaptive Fang attacks can undermine robustness; validate the Byzantine bound locally.",
    references=("https://proceedings.mlr.press/v80/yin18a.html",),
    translations={
        "it": {
            "limitations": "Le ipotesi valgono in ogni gruppo di aggregazione. Update onesti non-IID, ALIE e Fang adattivo possono compromettere la robustezza; verificare localmente il limite bizantino.",
            "title": "Trimmed mean",
            "description": "Esclude k estremi per lato in ciascuna coordinata.",
        }
    },
)
