"""Bound-constrained Byzantine attacks of Shejwalkar & Houmansadr (NDSS 2021).

Works on local-model vectors (not gradients). Geometry constraints are computed
from the attacker-visible reference population, not invented benign updates.
"""

import numpy as np


def constrained_perturbation(matrix, global_vector, *, objective, iterations=32):
    """Create a malicious local-model vector with a bounded standard-deviation direction.

    Min-Max: max_j ||m - x_j||² <= max_{i,j} ||x_i - x_j||².
    Min-Sum: sum_j ||m - x_j||² <= max_i sum_j ||x_i - x_j||².
    A binary search finds the largest feasible lambda along -std(matrix).
    """
    if matrix.ndim != 2 or len(matrix) < 2:
        raise ValueError("Min-Max/Min-Sum requires at least two visible reference updates")
    if not np.isfinite(matrix).all():
        raise ValueError("Non-finite reference updates")
    center = matrix.mean(axis=0)
    direction = matrix.std(axis=0, ddof=0)
    length = float(np.linalg.norm(direction))
    if length == 0.0:
        return center.copy(), 0.0, True
    offsets = matrix[:, None, :] - matrix[None, :, :]
    distances = np.einsum("ijk,ijk->ij", offsets, offsets)
    bound = float(np.max(distances) if objective == "min_max" else np.max(distances.sum(axis=1)))
    if objective not in ("min_max", "min_sum"):
        raise ValueError("Unknown distance objective")

    def feasible(lam):
        difference = (center - lam * direction)[None, :] - matrix
        squares = np.einsum("ij,ij->i", difference, difference)
        observed = float(np.max(squares) if objective == "min_max" else np.sum(squares))
        return observed <= bound + 1e-10 * max(1.0, bound)

    if not feasible(0.0):
        return center.copy(), 0.0, False
    lo, hi = 0.0, 1.0
    while feasible(hi) and hi < 1e6:
        lo, hi = hi, hi * 2.0
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        if feasible(mid):
            lo = mid
        else:
            hi = mid
    return center - lo * direction, float(lo), True
