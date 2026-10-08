import numpy as np
from atima_fl.core.contracts import Component


def apply(matrix, params):
    norms = np.linalg.norm(matrix, axis=1)
    factors = np.minimum(1.0, params["clip_norm"] / np.maximum(norms, 1e-12))
    return matrix * factors[:, None], {"factors": factors.tolist(), "input_norms": norms.tolist()}


PLUGIN = Component(
    "norm_clipping",
    "defense",
    "L2 clipping",
    "Limits each delta norm before aggregation.",
    {"clip_norm": {"type": "number", "default": 10.0, "minimum": 0.000001}},
    {"apply": apply},
    translations={
        "it": {
            "title": "Clipping L2",
            "description": "Limita la norma di ciascun delta prima dell’aggregazione.",
        }
    },
)
