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
    "Mediana",
    "Mediana coordinata per coordinata, senza pesi di numerosità.",
    hooks={"aggregate": aggregate},
)
