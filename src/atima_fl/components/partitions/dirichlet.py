"""Select an explicitly prepared and audited Dirichlet partition.

Changing alpha never silently reuses the alpha=0.5 client shards. Preparation
and split integrity are independently verified by the dataset's audit hook.
"""
from decimal import Decimal, InvalidOperation

from atima_fl.core.contracts import Component


def alpha_directory(alpha):
    try:
        value = Decimal(str(alpha))
    except InvalidOperation as exc:
        raise ValueError("Dirichlet alpha must be a valid number") from exc
    if not value.is_finite() or value <= 0 or value > 100:
        raise ValueError("Dirichlet alpha must be in (0, 100]")
    return format(value.normalize(), "f")


def validate(config, params):
    """Reject invalid Dirichlet values during TOML/UI validation."""
    alpha_directory(params["alpha"])


def location(root, config, params):
    alpha = alpha_directory(params["alpha"])
    # Preserve compatibility with the audited historical alpha=0.5 corpus.
    if alpha == "0.5":
        return root / "dirichlet"
    # Non-default alphas must have their own immutable persisted shards.
    return root / ("dirichlet_alpha_" + alpha)


PLUGIN = Component(
    "dirichlet",
    "partition",
    "Persisted Dirichlet partition (selectable α)",
    "Selects a verified persisted Dirichlet partition for the chosen alpha. "
    "For alpha=0.5 the historic 'dirichlet' directory is used; other values "
    "require an independently prepared 'dirichlet_alpha_<alpha>' directory. "
    "ATIMA never relabels alpha=0.5 shards as a different alpha.",
    {"alpha": {"type": "number", "default": 0.5, "min": 0.01, "max": 100.0}},
    {"location": location, "validate": validate},
    translations={
        "it": {
            "title": "Partizione Dirichlet persistita (α selezionabile)",
            "description": "Seleziona shard già preparati e verificati per il valore α. "
            "α=0,5 usa la cartella storica 'dirichlet'; valori diversi "
            "richiedono una cartella distinta 'dirichlet_alpha_<alpha>'.",
        }
    },
)
