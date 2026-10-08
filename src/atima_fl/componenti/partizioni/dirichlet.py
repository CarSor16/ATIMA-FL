from atima_fl.core.contracts import Component


def location(root, config, params):
    return root / "dirichlet"


PLUGIN = Component(
    "dirichlet",
    "partition",
    "Dirichlet α=0,5 persistita",
    "Usa esclusivamente gli shard α=0,5 già preparati. α=0,1 richiede una partizione verificata distinta.",
    {"alpha": {"type": "number", "default": 0.5, "choices": [0.5]}},
    {"location": location},
)
