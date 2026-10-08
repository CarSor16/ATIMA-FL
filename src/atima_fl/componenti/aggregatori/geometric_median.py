"""Centralized smoothed Weiszfeld on deltas; no secure-aggregation implementation."""

import numpy as np
from atima_fl.core.contracts import Component


def aggregate(matrix, counts, params):
    alpha = (
        np.asarray(counts, dtype=float)
        if params["weighting"] == "samples"
        else np.ones(len(matrix))
    )
    alpha /= alpha.sum()
    value = alpha @ matrix
    converged = False
    for step in range(params["iterations"]):
        distances = np.linalg.norm(matrix - value, axis=1)
        beta = alpha / np.maximum(params["smoothing"], distances)
        candidate = (beta / beta.sum()) @ matrix
        shift = float(np.linalg.norm(candidate - value))
        tolerance = params["tolerance"] * max(1.0, float(np.linalg.norm(value)))
        value = candidate
        if shift <= tolerance:
            converged = True
            break
    return value, {
        "iterations": step + 1,
        "converged": converged,
        "last_shift_l2": shift,
        "weighting": params["weighting"],
        "weighted_distance_objective": float(alpha @ np.linalg.norm(matrix - value, axis=1)),
        "selection_scope": "smoothed_geometric_median",
        "selected_indices": None,
    }


PLUGIN = Component(
    "geometric_median",
    "aggregator",
    "Smoothed geometric median (RFA-inspired)",
    "Smoothed Weiszfeld over client deltas, initialized at their weighted mean.",
    {
        "iterations": {"type": "integer", "default": 20, "minimum": 1, "maximum": 1000},
        "smoothing": {"type": "number", "default": 1e-6, "minimum": 1e-12},
        "tolerance": {"type": "number", "default": 1e-6, "minimum": 0},
        "weighting": {"type": "string", "default": "uniform", "choices": ["uniform", "samples"]},
    },
    {"aggregate": aggregate},
    mitigates=("byzantine_update", "large_norm", "coordinate_outlier"),
    limitations="Centralized numerical adaptation, not the paper's secure aggregation protocol. Robustness depends on honest weight mass and bounded heterogeneity; finite iterations are approximate.",
    references=("https://arxiv.org/abs/1912.13445",),
    translations={
        "it": {
            "title": "Mediana geometrica regolarizzata (ispirata a RFA)",
            "description": "Weiszfeld regolarizzato sui delta dei client, inizializzato dalla media pesata.",
            "limitations": "Adattamento numerico centralizzato, senza secure aggregation del paper. Robustezza legata alla massa onesta e all'eterogeneità; iterazioni finite danno un'approssimazione.",
        }
    },
)
