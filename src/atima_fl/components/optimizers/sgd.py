from atima_fl.core.contracts import Component


def build(parameters, config, params):
    import torch

    return torch.optim.SGD(
        parameters,
        lr=config.learning_rate,
        momentum=params["momentum"],
        weight_decay=params["weight_decay"],
    )


PLUGIN = Component(
    "sgd",
    "optimizer",
    "SGD",
    "SGD with optional momentum; state is recreated at every fit.",
    {
        "momentum": {"type": "number", "default": 0.0, "minimum": 0, "maximum": 0.999999},
        "weight_decay": {"type": "number", "default": 0.0, "minimum": 0},
    },
    {"build": build},
    translations={
        "it": {
            "title": "SGD",
            "description": "SGD con momentum opzionale; stato ricreato a ogni fit.",
        }
    },
)
