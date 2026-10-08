from atima_fl.core.vector import restore
from atima_fl.core.contracts import Component
from atima_fl.engine.attacks import statistics_craft, statistical_knowledge
from statistics import NormalDist
import math


def craft(
    matrix, global_vector, raw_by_client, local_arrays, global_arrays, config, client, round_id
):
    n, f = config.clients, len(config.malicious_clients)
    supporters = math.floor(n / 2 + 1) - f
    fraction = (n - f - supporters) / (n - f)
    zmax = NormalDist().inv_cdf(fraction)
    if zmax < 0:
        raise ValueError("ALIE automatic perturbation range is negative")
    z = zmax if config.alie_z == -1 else config.alie_z
    # Algorithm 3 uses mean - z*sigma. Oracle variant replaces only estimator.
    poisoned = matrix.mean(axis=0) - z * matrix.std(axis=0, ddof=0)
    info = {
        "attack_applied": True,
        "z": z,
        "zmax": zmax,
        "within_paper_bound": z <= zmax,
        "degenerate_z_range": zmax == 0,
        "knowledge": config.knowledge,
    }
    return restore(poisoned, global_arrays), info


def validate(config, params):
    if params["alie_z"] != -1 and params["alie_z"] < 0:
        raise ValueError("ALIE z=-1 means auto, otherwise use z>=0")
    if params["knowledge"] == "local" and len(config.malicious_clients) < 2:
        raise ValueError("Local ALIE needs at least two colluding clients")
    n, f = config.clients, len(config.malicious_clients)
    if n - f <= 0 or not 0 < (n - f - math.floor(n / 2 + 1) + f) / (n - f) < 1:
        raise ValueError("Invalid ALIE supporter probability")


def transform(context):
    return statistics_craft(context, craft)


def warnings(config, params):
    n, f = config.clients, len(config.malicious_clients)
    fraction = (n - f - math.floor(n / 2 + 1) + f) / (n - f)
    if fraction <= 0.5:
        return [
            "ALIE: the automatic z bound is zero or negative; a null effect is not evidence of robustness."
        ]
    return []


PLUGIN = Component(
    "alie",
    "attack",
    "ALIE",
    "Statistical perturbation using colluding updates; automatic z may be degenerate.",
    {
        "knowledge": {"type": "string", "default": "local", "choices": ["local", "oracle"]},
        "alie_z": {"type": "number", "default": -1.0, "minimum": -1},
    },
    {
        "validate": validate,
        "knowledge": statistical_knowledge,
        "transform": transform,
        "warnings": warnings,
    },
    references=(
        "https://proceedings.neurips.cc/paper/2019/file/ec1c59141046cd1866bbbcdfb6ae31d4-Paper.pdf",
    ),
    threats=("stealth_poisoning", "byzantine_update"),
    translations={
        "it": {
            "title": "ALIE",
            "description": "Perturbazione statistica dei collusi; z automatico può essere degenere.",
        }
    },
)
