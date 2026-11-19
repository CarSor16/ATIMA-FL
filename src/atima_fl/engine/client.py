"""Client work, independent of Flower and of specific attack IDs."""

import time
import numpy as np
from atima_fl.core.contracts import AttackContext
from atima_fl.engine.attacks import knowledge_ids, prepare_training, poison_update
from atima_fl.engine.models import attackable_indices, metrics, probabilities, train
from atima_fl.engine.storage import raw_path, write_raw, read_raw



def _training_data_altered(original, batch):
    """Preserve the existing base-sample comparison semantics."""
    return (
        len(batch.y) != len(original.y)
        or not np.array_equal(batch.x[: len(original.y)], original.x)
        or not np.array_equal(batch.y[: len(original.y)], original.y)
    )


def _merge_attack_metadata(metadata, attack_notes):
    """Retain data-stage attack evidence when update poisoning does not apply."""
    prepared_applied = metadata.get("attack_applied", False)
    metadata.update(attack_notes)
    metadata["attack_applied"] = prepared_applied or attack_notes.get("attack_applied", False)



def _local_train_metrics(config, client, round_id, local, batch, data, device, client_state):
    """Loss/accuracy of this client's own model on the shard it just trained on.

    One inference pass, no gradients and no randomness: the local model and the
    global trajectory are untouched, so the aggregated metrics of the run cannot
    change. Kept out of `metrics()`'s server-side use because here the target is
    the client's own training data, not a held-out split.
    """
    if config.training_method == "hyperfl_plus_plus":
        from atima_fl.engine.hyperfl import local_train_metrics

        return local_train_metrics(
            config, client, round_id, local, client_state, batch.x, batch.y, device, data.classes
        )
    p = probabilities(local, batch.x, config, device)
    result = metrics(batch.y, p, data.classes, config)
    return {key: float(result[key]) for key in ("loss", "accuracy", "macro_f1")}


def train_local(config, run, client, round_id, before, data, device, client_state=None):
    original = data.shard(client)
    context = AttackContext(config, client, round_id)
    batch = prepare_training(original.x, original.y, context)
    started = time.perf_counter()
    private_state = None
    if config.training_method == "hyperfl_plus_plus":
        from atima_fl.engine.hyperfl import train_local as train_hyperfl

        local, private_state = train_hyperfl(
            config, client, round_id, before, batch.x, batch.y, device, client_state
        )
        if client_state is not None:
            client_state.clear()
            client_state.update(private_state)
    else:
        local = train(before, batch.x, batch.y, config, client, round_id, device)
    local_metrics = _local_train_metrics(
        config, client, round_id, local, batch, data, device, private_state
    )
    registry = config.registry()
    params = registry.parameters("attack", config.attack, config.attack_params)
    metadata = {
        "local_loss": local_metrics["loss"],
        "local_accuracy": local_metrics["accuracy"],
        "local_macro_f1": local_metrics["macro_f1"],
        "local_metrics_split": "client's own training shard, inference only",
        "client": client,
        "aggregation_server": config.server_assignment()[client],
        "round": round_id,
        "is_malicious": config.attack != "none" and client in config.malicious_clients,
        "attack": config.attack if context.active else "none",
        "active": context.active,
        "attack_parameters": params if context.active else {},
        "train_seconds": time.perf_counter() - started,
        "original_samples": len(original.y),
        "trained_samples": len(batch.y),
        "poisoned_labels": len(batch.changed_label_indices),
        "backdoor_added_samples": len(batch.added_sample_indices),
        "device": str(device),
        "training_method": config.training_method,
        "local_update_is_clean_counterfactual": config.attack == "none",
        "local_reference_scope": "local training conditional on incoming global; attacked runs are not paired-clean counterfactuals",
        **batch.notes,
    }
    metadata["local_training_data_altered"] = _training_data_altered(original, batch)
    # Base-sample trained labels are stored separately from appended trigger copies.
    write_raw(
        raw_path(run, round_id, client),
        local,
        original.y,
        batch.y[: len(original.y)],
        original.source_ids,
        batch.changed_label_indices,
        metadata,
    )
    return local, metadata


def submit_local(config, run, client, round_id, before, counts, client_state=None):
    local, metadata, _ = read_raw(raw_path(run, round_id, client))
    context = AttackContext(
        config,
        client,
        round_id,
        before,
        local,
        counts=counts,
        attackable_indices=(
            tuple(range(len(before)))
            if config.training_method == "hyperfl_plus_plus"
            else attackable_indices(config)
        ),
    )
    context.run_dir = run
    context.client_state = client_state
    context.raw_by_client = {
        cid: read_raw(raw_path(run, round_id, cid))[0] for cid in knowledge_ids(context)
    }
    submitted, attack_notes = poison_update(context)
    _merge_attack_metadata(metadata, attack_notes)
    metadata["submitted_differs_from_local"] = any(
        not np.array_equal(a, b) for a, b in zip(submitted, local)
    )
    return submitted, metadata
