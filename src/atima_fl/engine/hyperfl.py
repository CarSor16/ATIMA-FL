"""Optional HyperFL++ protocol primitives for LopezCNN.

Only the RKD hypernetwork is returned to the coordinator. Client embeddings,
classifier parameters and BatchNorm running statistics remain in Flower Context.
"""
import math


def _factor_pair(size):
    left = math.isqrt(size)
    while size % left:
        left -= 1
    return left, size // left


def _model(config, seed):
    from atima_fl.engine.models import build

    return build(config, seed)


def _hypernetwork(config, seed):
    import torch
    from torch import nn

    torch.manual_seed(seed)
    reference = _model(config, seed)
    shapes = {
        name: tuple(parameter.shape)
        for name, parameter in reference.named_parameters()
        if not name.startswith("fc.")
    }

    class RKDLinear(nn.Module):
        def __init__(self, name, shape, hidden):
            super().__init__()
            size = math.prod(shape)
            d1, d2 = _factor_pair(size)
            self.left = nn.Parameter(torch.empty(hidden, d1))
            self.right = nn.Parameter(torch.empty(hidden, d2))
            self.bias_left = nn.Parameter(torch.empty(d1))
            self.bias_right = nn.Parameter(torch.empty(d2))
            nn.init.normal_(self.left, std=1 / math.sqrt(d1))
            nn.init.normal_(self.right, std=1 / math.sqrt(d2))
            nn.init.zeros_(self.bias_left)
            nn.init.normal_(self.bias_right, std=1 / math.sqrt(d2))
            self.shape = shape
            fan_in = math.prod(shape[1:]) if len(shape) > 1 else size
            self.scale = math.sqrt(2 * shape[0] / hidden) if name.endswith(".weight") and len(shape) > 1 else math.sqrt(shape[0] / hidden)
            if name.rsplit(".", 1)[0].startswith("bn") and name.endswith(".weight"):
                self.scale = 0.05
                self.offset = 1.0
            else:
                self.offset = 0.0
            if name.endswith(".bias"):
                self.scale = math.sqrt(shape[0] / hidden) / math.sqrt(max(fan_in, 1))

        def forward(self, features):
            outer = torch.bmm(self.left.unsqueeze(2), self.right.unsqueeze(1)).reshape(self.left.shape[0], -1)
            bias = torch.outer(self.bias_left, self.bias_right).reshape(1, -1)
            return ((features @ outer) * self.scale + bias).reshape(self.shape) + self.offset

    class HyperNetwork(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(16, 64),
                nn.ReLU(),
            )
            self.generators = nn.ModuleDict({
                f"p{index}": RKDLinear(name, shape, 64)
                for index, (name, shape) in enumerate(shapes.items())
            })

        def forward(self, embedding):
            features = self.encoder(embedding.reshape(1, -1))
            return {
                name: self.generators[f"p{index}"](features).squeeze(0)
                for index, name in enumerate(shapes)
            }

    return HyperNetwork(), shapes


def initial_shared_arrays(config):
    import numpy as np

    network, _ = _hypernetwork(config, config.seed)
    return [value.detach().cpu().numpy().copy() for value in network.state_dict().values()]


def _load_arrays(network, values):
    import numpy as np
    import torch

    state = network.state_dict()
    if len(values) != len(state):
        raise ValueError("HyperFL++ shared parameter count changed")
    for key, value in zip(state, values):
        array = np.asarray(value)
        if array.shape != tuple(state[key].shape) or not np.isfinite(array).all():
            raise ValueError(f"Invalid HyperFL++ shared parameter: {key}")
        state[key] = torch.as_tensor(array.copy(), dtype=state[key].dtype)
    network.load_state_dict(state)


def _private_state(model, shapes, existing, client, seed):
    import numpy as np
    import torch

    parameter_names = set(shapes)
    names = [
        name for name in model.state_dict()
        if name not in parameter_names
    ]
    if existing is not None:
        if set(existing) != set(names) | {"__embedding__"}:
            raise ValueError("Stored HyperFL++ client state has an incompatible schema")
        values = existing
    else:
        torch.manual_seed(seed + client)
        values = {
            name: value.detach().cpu().numpy().copy()
            for name, value in model.state_dict().items()
            if name in names
        }
        embedding = torch.empty(16)
        nn_init = torch.nn.init
        nn_init.normal_(embedding, std=0.02)
        values["__embedding__"] = embedding.numpy().copy()
    state = model.state_dict()
    for name in names:
        value = np.asarray(values[name])
        if value.shape != tuple(state[name].shape) or not np.isfinite(value).all():
            raise ValueError(f"Invalid private HyperFL++ state: {name}")
        state[name] = torch.as_tensor(value.copy(), dtype=state[name].dtype)
    model.load_state_dict(state)
    return values


def _live_state(model, shapes, device):
    return {
        **{name: value for name, value in model.named_parameters()},
        **{name: value for name, value in model.named_buffers()},
    }


def train_local(config, client, round_id, before, x, y, device, client_state=None):
    import numpy as np
    import torch
    from torch.func import functional_call
    from atima_fl.core.numerics import round_seed

    seed = round_seed(config.seed, client, round_id)
    torch.manual_seed(seed)
    model = _model(config, seed).to(device)
    network, shapes = _hypernetwork(config, config.seed)
    network.to(device)
    _load_arrays(network, before)
    private = _private_state(
        model, shapes, client_state, client, round_seed(config.seed, client, 0)
    )
    embedding = torch.as_tensor(
        np.asarray(private["__embedding__"]).copy(), dtype=torch.float32, device=device
    ).requires_grad_(True)
    private_names = set(model.state_dict()) - set(shapes)
    state = _live_state(model, shapes, device)
    optimizer_plugin = config.registry().get("optimizer", config.optimizer)
    optimizer_params = config.registry().parameters(
        "optimizer", config.optimizer, config.optimizer_params
    )
    head_optimizer = optimizer_plugin.hooks["build"](
        list(model.fc.parameters()), config, optimizer_params
    )
    shared_optimizer = optimizer_plugin.hooks["build"](
        list(network.parameters()) + [embedding], config, optimizer_params
    )
    criterion = config.registry().get("loss", config.loss).hooks["build"](
        config, config.registry().parameters("loss", config.loss, config.loss_params)
    )
    rng = np.random.default_rng(seed)
    model.train()
    epochs = config.local_epochs
    if epochs < 2:
        raise ValueError("HyperFL++ needs at least two local epochs (head plus generated features)")
    for epoch in range(epochs):
        order = rng.permutation(len(y))
        for start in range(0, len(y), config.batch_size):
            indices = order[start : start + config.batch_size]
            xb = torch.from_numpy(np.ascontiguousarray(x[indices])).to(device)
            yb = torch.from_numpy(np.ascontiguousarray(y[indices])).long().to(device)
            if epoch == 0:
                generated = {key: value.detach() for key, value in network(embedding).items()}
                state.update(generated)
                head_optimizer.zero_grad(set_to_none=True)
                logits = functional_call(model, state, (xb,))
                loss = criterion(logits, yb)
                if not torch.isfinite(loss).item():
                    raise ValueError("Nonfinite HyperFL++ classifier loss")
                loss.backward()
                head_optimizer.step()
            else:
                shared_optimizer.zero_grad(set_to_none=True)
                generated = network(embedding)
                state.update(generated)
                logits = functional_call(model, state, (xb,))
                loss = criterion(logits, yb)
                if not torch.isfinite(loss).item():
                    raise ValueError("Nonfinite HyperFL++ feature loss")
                loss.backward()
                shared_optimizer.step()
    private = {
        name: value.detach().cpu().numpy().copy()
        for name, value in state.items()
        if name in private_names
    }
    private["__embedding__"] = embedding.detach().cpu().numpy().copy()
    shared = [value.detach().cpu().numpy().copy() for value in network.state_dict().values()]
    if any(not np.isfinite(value).all() for value in shared + list(private.values())):
        raise ValueError("Nonfinite HyperFL++ state")
    return shared, private


def evaluate_local(config, client, round_id, shared, data, device, client_state, split):
    import numpy as np
    import torch
    from torch.func import functional_call
    from atima_fl.engine.models import metrics

    if not client_state:
        raise ValueError("HyperFL++ client-private state is missing")
    model = _model(config, config.seed + client).to(device).eval()
    network, shapes = _hypernetwork(config, config.seed)
    network.to(device)
    _load_arrays(network, shared)
    private = _private_state(model, shapes, client_state, client, config.seed)
    embedding = torch.as_tensor(
        np.asarray(private["__embedding__"]).copy(), dtype=torch.float32, device=device
    )
    state = _live_state(model, shapes, device)
    network.eval()
    part = data.split(split)
    outputs = []
    with torch.inference_mode():
        state.update(network(embedding))
        for start in range(0, len(part.y), 1024):
            xb = torch.from_numpy(np.ascontiguousarray(part.x[start : start + 1024])).to(device)
            outputs.append(torch.softmax(functional_call(model, state, (xb,)), dim=1).cpu().numpy())
    probabilities = np.concatenate(outputs) if outputs else np.empty((0, config.num_classes))
    result = metrics(part.y, probabilities, data.classes, config)
    return result, {
        "client": client,
        "round": round_id,
        "aggregation_server": config.server_assignment()[client],
        "device": str(device),
        "evaluation": result,
    }


def aggregate_personalized(results, classes):
    import numpy as np

    matrix = np.sum(
        [np.asarray(item["evaluation"]["confusion_matrix"], dtype=np.int64) for item in results],
        axis=0,
    )
    support = matrix.sum(axis=1)
    predicted = matrix.sum(axis=0)
    total = int(matrix.sum())
    tp = np.diag(matrix)
    recall = np.divide(tp, support, out=np.zeros(len(classes), dtype=float), where=support > 0)
    precision = np.divide(tp, predicted, out=np.zeros(len(classes), dtype=float), where=predicted > 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(len(classes), dtype=float), where=(precision + recall) > 0)
    weighted_f1 = float(np.average(f1, weights=support)) if total else 0.0
    denominator = math.sqrt(
        max(total * total - float(predicted @ predicted), 0.0)
        * max(total * total - float(support @ support), 0.0)
    )
    mcc = float((total * float(tp.sum()) - float(predicted @ support)) / denominator) if denominator else 0.0
    loss = sum(
        item["evaluation"]["loss"] * item["evaluation"]["samples"] for item in results
    ) / max(total, 1)
    per_class = {
        name: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1-score": float(f1[index]),
            "support": int(support[index]),
        }
        for index, name in enumerate(classes)
    }
    return {
        "accuracy": float(tp.sum() / max(total, 1)),
        "macro_f1": float(f1.mean()),
        "weighted_f1": weighted_f1,
        "balanced_accuracy": float(recall.mean()),
        "mcc": mcc,
        "loss": float(loss),
        "recall": recall.tolist(),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
        "samples": total,
        "loss_definition": "sample-weighted mean of client-local cross-entropy",
        "personalized_models": len(results),
        "client_macro_f1_mean": float(np.mean([v["evaluation"]["macro_f1"] for v in results])),
        "client_macro_f1_min": float(np.min([v["evaluation"]["macro_f1"] for v in results])),
    }
