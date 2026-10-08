"""Client-side component dispatch. This module contains no attack ID switches."""

from dataclasses import asdict
from types import SimpleNamespace
import numpy as np
from atima_fl.core.contracts import AttackContext, TrainingBatch
from atima_fl.core.numerics import check_arrays


def active(config, client, round_id):
    return AttackContext(config, client, round_id).active


def view(config):
    values = asdict(config)
    values.update(config.parameters("attack"))
    values.update(config.parameters("aggregator"))
    return SimpleNamespace(**values)


def component(context):
    return context.config.registry().get("attack", context.config.attack)


def knowledge_ids(context):
    if not context.active:
        return [context.client]
    hook = component(context).hooks.get("knowledge")
    ids = list(hook(context)) if hook else [context.client]
    if not ids or any(type(cid) is not int or not 0 <= cid < context.config.clients for cid in ids):
        raise ValueError("Attack requested invalid logical knowledge IDs")
    return ids


def prepare_training(x, y, context):
    empty = np.empty(0, dtype=np.int64)
    batch = TrainingBatch(x.copy(), y.copy(), empty, empty)
    hook = component(context).hooks.get("prepare")
    if context.active and hook:
        batch = hook(x.copy(), y.copy(), context)
    if batch.x.shape != (len(batch.y), context.config.input_dim) or not np.isfinite(batch.x).all():
        raise ValueError("Attack produced invalid training inputs")
    if not np.isin(batch.y, range(context.config.num_classes)).all():
        raise ValueError("Attack produced invalid labels")
    return batch


def poison_update(context):
    check_arrays(context.local_arrays, context.global_arrays)
    hook = component(context).hooks.get("transform")
    if not context.active or hook is None:
        return [a.copy() for a in context.local_arrays], {"attack_applied": False}
    indices = context.attackable_indices
    if not indices:
        raise ValueError("Model did not declare attackable parameters")
    scoped = AttackContext(
        context.config,
        context.client,
        context.round_id,
        [context.global_arrays[i].copy() for i in indices],
        [context.local_arrays[i].copy() for i in indices],
        {cid: [values[i].copy() for i in indices] for cid, values in context.raw_by_client.items()},
        context.counts,
        tuple(range(len(indices))),
    )
    values, info = hook(scoped)
    check_arrays(values, scoped.global_arrays)
    submitted = [a.copy() for a in context.local_arrays]
    for index, value in zip(indices, values):
        submitted[index] = value
    info["parameter_scope"] = "trainable_parameters"
    info["submitted_differs_from_local"] = any(
        not np.array_equal(a, b) for a, b in zip(submitted, context.local_arrays)
    )
    return submitted, info


def statistics_craft(context, craft):
    from atima_fl.core.vector import flatten

    config = view(context.config)
    ids = (
        [cid for cid in sorted(context.raw_by_client) if cid not in config.malicious_clients]
        if config.knowledge == "oracle"
        else list(config.malicious_clients)
    )
    if not ids or any(cid not in context.raw_by_client for cid in ids):
        raise ValueError("Declared attack knowledge is unavailable")
    matrix = np.stack([flatten(context.raw_by_client[cid]) for cid in ids])
    return craft(
        matrix,
        flatten(context.global_arrays),
        context.raw_by_client,
        context.local_arrays,
        context.global_arrays,
        config,
        context.client,
        context.round_id,
    )


def statistical_knowledge(context):
    knowledge = context.config.parameters("attack")["knowledge"]
    return (
        list(range(context.config.clients))
        if knowledge == "oracle"
        else list(context.config.malicious_clients)
    )
