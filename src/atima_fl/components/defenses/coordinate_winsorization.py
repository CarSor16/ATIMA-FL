"""Generic median/MAD coordinate bounding; neither client detection nor row removal."""

import numpy as np
from atima_fl.core.contracts import Component


def apply(matrix, params):
    center = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - center), axis=0)
    radius = params["scale"] * np.maximum(mad, params["minimum_mad"])
    bounded = np.clip(matrix, center - radius, center + radius)
    changed = bounded != matrix
    return bounded, {
        "modified_coordinates": int(changed.sum()),
        "modified_clients": int(np.any(changed, axis=1).sum()),
        "zero_mad_coordinates": int(np.count_nonzero(mad == 0)),
        "definition": "clip around coordinate median +/- scale*max(MAD,minimum_mad); no 1.4826 correction",
    }


PLUGIN = Component(
    "coordinate_winsorization",
    "defense",
    "Coordinate median/MAD bounding",
    "Bounds each coordinate around its median using MAD; generic experimental preprocessing.",
    {
        "scale": {"type": "number", "default": 3.0, "minimum": 1e-6},
        "minimum_mad": {"type": "number", "default": 1e-6, "minimum": 1e-12},
    },
    {"apply": apply},
    mitigates=("coordinate_outlier", "byzantine_update"),
    limitations="Requires a useful majority in each group. Correlated low-amplitude attacks and heterogeneous honest updates can defeat or bias it. This is not a named-paper defense or a detector.",
    translations={
        "it": {
            "title": "Limitazione coordinata mediana/MAD",
            "description": "Limita ogni coordinata intorno alla mediana usando MAD; preprocessing sperimentale generico.",
            "limitations": "Serve una maggioranza utile in ciascun gruppo. Attacchi correlati a bassa ampiezza e update onesti eterogenei possono eluderla o introdurre bias. Non è un detector né una difesa specifica di un paper.",
        }
    },
)
