from atima_fl.core.contracts import Component


def build(parameters, config, params):
    import torch

    return torch.optim.Adam(
        parameters, lr=config.learning_rate, weight_decay=params["weight_decay"]
    )


PLUGIN = Component(
    "adam",
    "optimizer",
    "Adam",
    "Stato dell’ottimizzatore ricreato a ogni fit locale.",
    {"weight_decay": {"type": "number", "default": 0.0, "minimum": 0}},
    {"build": build},
)
