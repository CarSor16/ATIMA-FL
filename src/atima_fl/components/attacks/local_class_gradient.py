"""Local-only class-targeted model poisoning via bounded gradient ascent.

No benign client updates, server evaluation set, or labels outside the
compromised client's own shard are read. This is not a stealth guarantee.
"""
import numpy as np
from atima_fl.core.contracts import Component
from atima_fl.core.numerics import round_seed


def validate(config, params):
    if params["target_class"] >= config.num_classes:
        raise ValueError("Target class outside the classification task")


def transform(context):
    import torch
    import torch.nn.functional as F
    from atima_fl.engine.data import open_dataset
    from atima_fl.engine.models import build, set_arrays
    from atima_fl.engine.storage import raw_path, read_raw

    p = context.config.parameters("attack")
    shard = open_dataset(context.config).shard(context.client)
    eligible = np.flatnonzero(shard.y == p["target_class"])
    if len(eligible) == 0:
        return [a.copy() for a in context.local_arrays], {
            "attack_applied": False,
            "target_support": 0,
            "reason": "target_class_absent_from_compromised_shard",
            "knowledge": "local_shard_only",
        }
    rng = np.random.default_rng(
        round_seed(context.config.seed, context.client, context.round_id)
    )
    selected = np.sort(rng.choice(eligible, min(len(eligible), p["max_examples"]), replace=False))
    full_local, _, _ = read_raw(
        raw_path(context.run_dir, context.round_id, context.client)
    )
    model = build(context.config)
    set_arrays(model, full_local)
    device = context.config.compute_device
    model.to(device).eval()
    xb = torch.from_numpy(np.ascontiguousarray(shard.x[selected])).to(device)
    yb = torch.from_numpy(np.ascontiguousarray(shard.y[selected])).long().to(device)
    model.zero_grad(set_to_none=True)
    loss = F.cross_entropy(model(xb), yb)
    if not torch.isfinite(loss).item():
        raise ValueError("Non-finite local class loss")
    loss.backward()

    params = list(model.parameters())
    if len(params) != len(context.local_arrays):
        raise ValueError("Local gradient and trainable model parameter order mismatch")
    gradients = [
        v.grad.detach().cpu().numpy().copy() if v.grad is not None
        else np.zeros_like(a)
        for v, a in zip(params, context.local_arrays)
    ]
    if any(g.shape != a.shape or not np.isfinite(g).all()
           for g, a in zip(gradients, context.local_arrays)):
        raise ValueError("Invalid local target-class gradient")
    grad_norm = float(np.sqrt(sum(
        np.square(g.astype(np.float64)).sum() for g in gradients
    )))
    delta_norm = float(np.sqrt(sum(
        np.square((a - b).astype(np.float64)).sum()
        for a, b in zip(context.local_arrays, context.global_arrays)
    )))
    if grad_norm <= 1e-12 or delta_norm <= 1e-12:
        return [a.copy() for a in context.local_arrays], {
            "attack_applied": False,
            "reason": "zero_target_gradient_or_local_update",
            "target_support": int(len(eligible)),
            "knowledge": "local_shard_only",
        }
    scale = p["relative_budget"] * delta_norm / grad_norm
    values = [
        np.asarray(a + scale * g, dtype=a.dtype)
        for a, g in zip(context.local_arrays, gradients)
    ]
    return values, {
        "attack_applied": True,
        "target_class": p["target_class"],
        "target_support": int(len(eligible)),
        "used_target_examples": int(len(selected)),
        "gradient_l2": grad_norm,
        "local_delta_l2": delta_norm,
        "added_perturbation_l2_budget": p["relative_budget"] * delta_norm,
        "objective": "ascend_local_target_class_cross_entropy",
        "knowledge": "local_shard_only",
    }


PLUGIN = Component(
    "local_class_gradient", "attack", "Local class-targeted gradient ascent",
    "Increases loss on the compromised client's target-class samples while "
    "bounding the added trainable update relative to its own FedAvg delta.",
    {
        "target_class": {"type": "integer", "default": 1, "minimum": 0},
        "relative_budget": {"type": "number", "default": 0.5, "minimum": 0.000001, "maximum": 2.0},
        "max_examples": {"type": "integer", "default": 128, "minimum": 1, "maximum": 512},
    },
    {"validate": validate, "transform": transform},
    threats=("targeted_model_poisoning", "local_knowledge"),
    limitations="Requires target-class examples on the compromised client; may have "
                "no effect under non-IID absence. Bounded gradient ascent does not "
                "guarantee target recall loss, other-class preservation, or stealth.",
)
