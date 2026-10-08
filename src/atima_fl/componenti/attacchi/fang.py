from atima_fl.core.numerics import round_seed
from atima_fl.core.vector import flatten, restore, krum_scores
from atima_fl.core.contracts import Component
from atima_fl.engine.attacks import statistics_craft, statistical_knowledge
import math
import numpy as np


def craft(
    matrix, global_vector, raw_by_client, local_arrays, global_arrays, config, client, round_id
):
    all_matrix = np.stack([flatten(raw_by_client[cid]) for cid in sorted(raw_by_client)])
    if config.fang_variant == "krum":
        scores = krum_scores(all_matrix, config.byzantine_bound)
        selected = all_matrix[int(np.argmin(scores))]
        direction = np.where(selected - global_vector > 0, 1.0, -1.0)
        f, n, d = len(config.malicious_clients), config.clients, len(global_vector)
        distances = np.linalg.norm(matrix[:, None, :] - matrix[None, :, :], axis=2)
        np.fill_diagonal(distances, np.inf)
        nearest_sum = np.sort(distances, axis=1)[:, : n - f - 2].sum(axis=1).min()
        lam = nearest_sum / ((n - 2 * f - 1) * math.sqrt(d)) + np.linalg.norm(
            matrix - global_vector, axis=1
        ).max() / math.sqrt(d)
        found = False
        while lam >= 1e-5:
            candidate = global_vector - lam * direction
            trial = np.vstack([np.repeat(candidate[None, :], f, axis=0), matrix])
            if int(np.argmin(krum_scores(trial, config.byzantine_bound))) < f:
                found = True
                break
            lam /= 2
        if not found:
            # Failure is explicit: do not silently rename another heuristic Fang.
            return [a.copy() for a in local_arrays], {
                "attack_applied": False,
                "fang_no_solution": True,
                "lambda": lam,
            }
        poisoned = candidate
        info = {
            "attack_applied": True,
            "lambda": lam,
            "fang_variant": "krum_full_knowledge",
            "support_radius": 0.0,
        }
    else:
        # Sec.3.3/3.4: full-knowledge directional coordinate extremum sampling.
        direction = np.where(all_matrix.mean(axis=0) - global_vector > 0, 1.0, -1.0)
        low, high = matrix.min(axis=0), matrix.max(axis=0)
        lower = np.where(
            direction < 0, high, np.where(low > 0, low / config.fang_b, config.fang_b * low)
        )
        upper = np.where(
            direction < 0, np.where(high > 0, config.fang_b * high, high / config.fang_b), low
        )
        rng = np.random.default_rng(round_seed(config.seed, client, round_id))
        poisoned = rng.uniform(lower, upper)
        info = {
            "attack_applied": True,
            "fang_variant": "trimmed_mean_full_knowledge",
            "b": config.fang_b,
            "actual_aggregator": config.aggregation,
            "transfer": config.aggregation not in {"median", "trimmed_mean"},
        }
    return restore(poisoned, global_arrays), info


def validate(config, params):
    if len(config.malicious_clients) >= config.clients:
        raise ValueError("Fang requires benign reference clients")
    if params["fang_variant"] == "krum":
        bound = params["byzantine_bound"]
        if len(config.malicious_clients) != bound or config.clients <= 2 * bound + 2:
            raise ValueError("Fang-Krum requires f=malicious clients and n>=2f+3")
        aggregation_bound = config.parameters("aggregator").get("byzantine_bound", bound)
        if aggregation_bound != bound:
            raise ValueError("Fang crafting bound differs from aggregator bound")


def transform(context):
    return statistics_craft(context, craft)


PLUGIN = Component(
    "fang",
    "attack",
    "Fang",
    "Oracle crafting for trimmed mean/median or Krum; transfers are declared.",
    {
        "knowledge": {"type": "string", "default": "oracle", "choices": ["oracle"]},
        "fang_variant": {
            "type": "string",
            "default": "trimmed_mean",
            "choices": ["trimmed_mean", "krum"],
        },
        "fang_b": {"type": "number", "default": 2.0, "minimum": 1.000001},
        "byzantine_bound": {"type": "integer", "default": 2, "minimum": 0},
    },
    {"validate": validate, "knowledge": statistical_knowledge, "transform": transform},
    references=("https://www.usenix.org/system/files/sec20-fang.pdf",),
    translations={
        "it": {
            "title": "Fang",
            "description": "Crafting oracle per trimmed mean/median o Krum; trasferimenti dichiarati.",
        }
    },
)
