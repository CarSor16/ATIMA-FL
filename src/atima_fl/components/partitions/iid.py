from atima_fl.core.contracts import Component


def location(root, config, params):
    return root / "iid"


PLUGIN = Component(
    "iid",
    "partition",
    "Persisted IID",
    "Uses saved IID assignments and shards; does not regenerate the split.",
    hooks={"location": location},
    translations={
        "it": {
            "title": "IID persistita",
            "description": "Usa assegnazioni e shard IID già salvati; non rigenera lo split.",
        }
    },
)
