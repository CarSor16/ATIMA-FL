from atima_fl.core.contracts import Component


def build(config, params):
    import torch

    return torch.nn.CrossEntropyLoss(label_smoothing=params["label_smoothing"])


PLUGIN = Component(
    "cross_entropy",
    "loss",
    "Cross-entropy",
    "Multiclass classification loss.",
    {"label_smoothing": {"type": "number", "default": 0.0, "minimum": 0, "maximum": 1}},
    {"build": build},
    translations={
        "it": {"title": "Cross-entropy", "description": "Loss di classificazione multiclasse."}
    },
)
