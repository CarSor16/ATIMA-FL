from atima_fl.core.vector import restore
from atima_fl.core.contracts import Component
from atima_fl.engine.attacks import statistics_craft, statistical_knowledge


def craft(
    matrix, global_vector, raw_by_client, local_arrays, global_arrays, config, client, round_id
):
    mean_delta = (matrix - global_vector).mean(axis=0)
    poisoned = global_vector - config.ipm_epsilon * mean_delta
    info = {
        "attack_applied": True,
        "epsilon": config.ipm_epsilon,
        "knowledge": "oracle",
        "representation": "local_model_delta_adapter",
    }
    return restore(poisoned, global_arrays), info


def validate(config, params):
    if len(config.malicious_clients) >= config.clients:
        raise ValueError("IPM requires a nonempty benign oracle reference")


def transform(context):
    return statistics_craft(context, craft)


PLUGIN = Component(
    "ipm",
    "attack",
    "IPM",
    "Delta opposite to the oracle benign mean; adapted to multi-epoch training.",
    {
        "knowledge": {"type": "string", "default": "oracle", "choices": ["oracle"]},
        "ipm_epsilon": {"type": "number", "default": 0.5, "minimum": 0.000001},
    },
    {"validate": validate, "knowledge": statistical_knowledge, "transform": transform},
    references=("https://proceedings.mlr.press/v115/xie20a/xie20a.pdf",),
    translations={
        "it": {
            "title": "IPM",
            "description": "Delta opposto alla media benign oracle; adattamento al training multi-epoca.",
        }
    },
)
