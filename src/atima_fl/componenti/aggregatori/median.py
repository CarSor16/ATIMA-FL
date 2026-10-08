import numpy as np
from atima_fl.core.contracts import Component


def aggregate(matrix, counts, params):
    return np.median(matrix, axis=0), {
        "selected_indices": None,
        "selection_scope": "coordinatewise_median",
    }


PLUGIN = Component(
    "median",
    "aggregator",
    "Median",
    "Coordinatewise median without sample-count weights.",
    hooks={"aggregate": aggregate},
    mitigates=("byzantine_update", "coordinate_outlier"),
    limitations="Assumptions apply within each aggregation group. Non-IID honest updates, ALIE and adaptive Fang attacks can undermine robustness; validate the Byzantine bound locally.",
    references=("https://proceedings.mlr.press/v80/yin18a.html",),
    translations={
        "it": {
            "limitations": "Le ipotesi valgono in ogni gruppo di aggregazione. Update onesti non-IID, ALIE e Fang adattivo possono compromettere la robustezza; verificare localmente il limite bizantino.",
            "title": "Mediana",
            "description": "Mediana coordinata per coordinata, senza pesi di numerosità.",
        }
    },
)
