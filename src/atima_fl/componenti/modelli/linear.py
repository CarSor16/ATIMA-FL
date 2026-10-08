from atima_fl.core.contracts import Component


def build(config, params, seed):
    import torch

    torch.manual_seed(seed)
    return torch.nn.Linear(config.input_dim, config.num_classes)


PLUGIN = Component(
    "linear",
    "model",
    "Classificatore lineare",
    "Baseline softmax lineare; confronto di capacità e prova della sostituibilità del modello.",
    hooks={"build": build},
)
