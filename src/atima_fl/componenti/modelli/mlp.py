from atima_fl.core.contracts import Component


def validate(config, params):
    if not params["hidden"] or any(v < 1 for v in params["hidden"]):
        raise ValueError("MLP needs positive hidden dimensions")


def build(config, params, seed):
    import torch

    torch.manual_seed(seed)
    dimensions = [config.input_dim] + params["hidden"] + [config.num_classes]
    layers = []
    for index in range(len(dimensions) - 1):
        layers.append(torch.nn.Linear(dimensions[index], dimensions[index + 1]))
        if index < len(dimensions) - 2:
            layers.append(torch.nn.ReLU())
    return torch.nn.Sequential(*layers)


PLUGIN = Component(
    "mlp",
    "model",
    "MLP",
    "Rete feed-forward ReLU senza BatchNorm; baseline 64→32.",
    {"hidden": {"type": "array", "default": [64, 32], "items": {"type": "integer", "minimum": 1}}},
    {"validate": validate, "build": build},
)
