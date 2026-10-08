"""PyTorch training adapter using discovered model, optimizer, loss and metric components."""

import numpy as np
from atima_fl.core.numerics import check_arrays, round_seed


def build(config, seed=None):
    registry = config.registry()
    return registry.get("model", config.model).hooks["build"](
        config,
        registry.parameters("model", config.model, config.model_params),
        config.seed if seed is None else seed,
    )


def arrays(model):
    return [value.detach().cpu().numpy().copy() for value in model.state_dict().values()]


def attackable_indices(config):
    model = build(config)
    names = set(dict(model.named_parameters()))
    return tuple(i for i, key in enumerate(model.state_dict()) if key in names)


def set_arrays(model, values):
    import torch

    check_arrays(values, arrays(model))
    # Preserve PyTorch's per-module version metadata (including BatchNorm).
    state = model.state_dict()
    for key, value in zip(state, values):
        state[key] = torch.from_numpy(np.asarray(value).copy())
    model.load_state_dict(state)


def train(global_arrays, x, y, config, client, round_id, device):
    import torch

    seed = round_seed(config.seed, client, round_id)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    model = build(config, seed)
    set_arrays(model, global_arrays)
    model = model.to(device)
    registry = config.registry()
    optimizer = registry.get("optimizer", config.optimizer).hooks["build"](
        model.parameters(),
        config,
        registry.parameters("optimizer", config.optimizer, config.optimizer_params),
    )
    criterion = registry.get("loss", config.loss).hooks["build"](
        config, registry.parameters("loss", config.loss, config.loss_params)
    )
    rng = np.random.default_rng(seed)
    model.train()
    for _ in range(config.local_epochs):
        order = rng.permutation(len(y))
        for start in range(0, len(y), config.batch_size):
            indices = order[start : start + config.batch_size]
            xb = torch.from_numpy(np.ascontiguousarray(x[indices])).to(device)
            yb = torch.from_numpy(np.ascontiguousarray(y[indices])).to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(xb), yb)
            if not torch.isfinite(loss).item():
                raise ValueError("Nonfinite local loss")
            loss.backward()
            optimizer.step()
    result = arrays(model)
    check_arrays(result, global_arrays)
    return result


def probabilities(values, x, config, device, batch_size=1024):
    import torch

    model = build(config)
    set_arrays(model, values)
    model.to(device).eval()
    predictions = []
    with torch.inference_mode():
        for start in range(0, len(x), batch_size):
            batch = torch.from_numpy(np.ascontiguousarray(x[start : start + batch_size])).to(device)
            predictions.append(torch.softmax(model(batch), dim=1).cpu().numpy())
    if not predictions:
        raise ValueError("Cannot evaluate an empty input set")
    p = np.concatenate(predictions)
    if not np.isfinite(p).all() or not np.allclose(p.sum(axis=1), 1, atol=1e-5):
        raise ValueError("Nonfinite or invalid global probabilities")
    return p


def metrics(y, p, classes, config):
    registry = config.registry()
    return registry.get("metrics", config.metrics).hooks["evaluate"](
        y, p, classes, registry.parameters("metrics", config.metrics, config.metrics_params)
    )
