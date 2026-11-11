"""Min-Max: distance-constrained Byzantine model poisoning (NDSS 2021)."""

from atima_fl.core.contracts import Component
from atima_fl.core.vector import restore
from atima_fl.core.byzantine_bounds import constrained_perturbation
from atima_fl.engine.attacks import statistics_craft, statistical_knowledge


def craft(matrix, global_vector, raw_by_client, local_arrays, global_arrays, config, client, round_id):
    candidate, lam, feasible = constrained_perturbation(
        matrix, global_vector, objective="min_max"
    )
    if not feasible:
        return [a.copy() for a in local_arrays], {
            "attack_applied": False,
            "reason": "zero-perturbation candidate violates declared geometric bound",
            "knowledge": config.knowledge,
        }
    return restore(candidate, global_arrays), {
        "attack_applied": bool(lam),
        "lambda": lam,
        "objective": "min_max",
        "deviation": "coordinate_standard_deviation",
        "knowledge": config.knowledge,
        "representation": "local_model_vector",
    }


def validate(config, params):
    if params["knowledge"] != "oracle":
        raise ValueError("Min-Max currently requires explicit oracle knowledge")
    if config.clients - len(config.malicious_clients) < 2:
        raise ValueError("Min-Max requires at least two benign reference clients")


def transform(context):
    return statistics_craft(context, craft)


PLUGIN = Component(
    "min_max",
    "attack",
    "Min-Max",
    "Untargeted Byzantine poisoning constrained by min-max distances between benign local models.",
    {"knowledge": {"type": "string", "default": "oracle", "choices": ["oracle"]}},
    {"validate": validate, "knowledge": statistical_knowledge, "transform": transform},
    references=("https://www.ndss-symposium.org/ndss-paper/manipulating-the-byzantine-optimizing-model-poisoning-attacks-and-defenses-for-federated-learning/",),
    threats=("byzantine_update", "adaptive_poisoning"),
    translations={"it": {"title": "Min-Max", "description": "Poisoning Byzantine con vincolo geometrico Min-Max e conoscenza oracle dichiarata."}},
)
