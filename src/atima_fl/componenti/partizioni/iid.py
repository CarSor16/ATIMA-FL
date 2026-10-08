from atima_fl.core.contracts import Component


def location(root, config, params):
    return root / "iid"


PLUGIN = Component(
    "iid",
    "partition",
    "IID persistita",
    "Usa assegnazioni e shard IID già salvati; non rigenera lo split.",
    hooks={"location": location},
)
