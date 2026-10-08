"""Defense pipeline followed by one discovered aggregator; no role oracle is provided."""

import numpy as np
from atima_fl.core.numerics import check_arrays
from atima_fl.core.vector import flatten, restore


def aggregate(updates, counts, config):
    if (
        not updates
        or len(updates) != len(counts)
        or any(type(n) is not int or n <= 0 for n in counts)
    ):
        raise ValueError("Complete positive sample counts required")
    for update in updates:
        check_arrays(update, updates[0])
    matrix = np.stack([flatten(update) for update in updates])
    raw_norms = np.linalg.norm(matrix, axis=1).tolist()
    registry = config.registry()
    stages = []
    for stage in config.defenses:
        plugin = registry.get("defense", stage["id"])
        params = registry.parameters("defense", stage["id"], stage["params"])
        previous = matrix.shape
        matrix, notes = plugin.hooks["apply"](matrix.copy(), params)
        if matrix.shape != previous or not np.isfinite(matrix).all():
            raise ValueError("Defense changed update dimensions or introduced nonfinite values")
        stages.append({"id": stage["id"], "params": params, "audit": notes})
    plugin = registry.get("aggregator", config.aggregation)
    result, audit = plugin.hooks["aggregate"](
        matrix,
        counts,
        registry.parameters("aggregator", config.aggregation, config.aggregation_params),
    )
    return restore(result, updates[0]), {
        "aggregator": plugin.id,
        "defense_stages": stages,
        "raw_norms": raw_norms,
        "processed_norms": np.linalg.norm(matrix, axis=1).tolist(),
        **audit,
    }
