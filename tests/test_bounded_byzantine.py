"""Deterministic geometric checks for bounded Byzantine attack objectives."""

import numpy as np
import pytest
from atima_fl.core.byzantine_bounds import constrained_perturbation


@pytest.mark.parametrize("objective", ["min_max", "min_sum"])
def test_bounded_poisoning_obeys_observed_distance_limit(objective):
    benign = np.array([[1.0, 0.0], [1.5, 0.5], [2.0, 1.0], [2.4, 0.3]])
    poisoned, lam, feasible = constrained_perturbation(
        benign, np.zeros(2), objective=objective,
    )
    assert feasible and lam >= 0 and np.isfinite(poisoned).all()
    distances = ((benign[:, None, :] - benign[None, :, :]) ** 2).sum(axis=2)
    squared = ((benign - poisoned) ** 2).sum(axis=1)
    bound = distances.max() if objective == "min_max" else distances.sum(axis=1).max()
    observed = squared.max() if objective == "min_max" else squared.sum()
    assert observed <= bound + 1e-7


def test_geometric_reference_requires_sufficient_clients():
    with pytest.raises(ValueError, match="at least two"):
        constrained_perturbation(np.ones((1, 2)), np.zeros(2), objective="min_max")
