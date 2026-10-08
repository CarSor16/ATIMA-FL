import numpy as np
from atima_fl.core.contracts import Component


def aggregate(matrix, counts, params):
    return np.average(matrix, axis=0, weights=counts), {
        "selected_indices": list(range(len(matrix))),
        "selection_scope": "sample_weighted",
    }


PLUGIN = Component(
    "fedavg",
    "aggregator",
    "FedAvg",
    "Weighted mean using original client sample counts.",
    hooks={"aggregate": aggregate},
    translations={
        "it": {
            "title": "FedAvg",
            "description": "Media pesata per numerosità originale dei client.",
        }
    },
)
