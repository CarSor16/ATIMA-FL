from atima_fl.core.contracts import Component


def location(root, config, params):
    return root / "dirichlet"


PLUGIN = Component(
    "dirichlet",
    "partition",
    "Persisted Dirichlet α=0.5",
    "Uses only the prepared α=0.5 shards. α=0.1 requires a separate verified partition.",
    {"alpha": {"type": "number", "default": 0.5, "choices": [0.5]}},
    {"location": location},
    translations={
        "it": {
            "title": "Dirichlet α=0,5 persistita",
            "description": "Usa esclusivamente gli shard α=0,5 già preparati. α=0,1 richiede una partizione verificata distinta.",
        }
    },
)
