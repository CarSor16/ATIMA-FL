"""Generic quantile-based clipping, without differential privacy claims."""

import numpy as np
from atima_fl.core.contracts import Component


def apply(matrix, params):
    norms = np.linalg.norm(matrix, axis=1)
    bound = max(params["minimum_norm"], float(np.quantile(norms, params["quantile"])))
    factors = np.minimum(1.0, bound / np.maximum(norms, 1e-12))
    return matrix * factors[:, None], {
        "clip_norm": bound,
        "factors": factors.tolist(),
        "clipped_clients": int(np.count_nonzero(factors < 1)),
    }


PLUGIN = Component(
    "adaptive_clipping",
    "defense",
    "Adaptive L2 clipping",
    "Caps update norms at a declared quantile of the current group; generic experimental variant.",
    {
        "quantile": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1},
        "minimum_norm": {"type": "number", "default": 1e-6, "minimum": 1e-12},
    },
    {"apply": apply},
    mitigates=("large_norm", "backdoor"),
    limitations="The threshold uses potentially corrupted updates. Low-norm poisoning survives; legitimate non-IID updates may be clipped. No DP guarantee.",
    references=("https://arxiv.org/abs/1911.07963",),
    translations={
        "it": {
            "title": "Clipping L2 adattivo",
            "description": "Limita le norme a un quantile dichiarato del gruppo corrente; variante sperimentale generica.",
            "limitations": "La soglia usa update potenzialmente corrotti. Poisoning a norma bassa può passare; client non-IID legittimi possono essere limitati. Nessuna garanzia DP.",
        }
    },
)
