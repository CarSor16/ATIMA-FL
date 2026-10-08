"""Client work, independent of Flower and of specific attack IDs."""

import time
import numpy as np
from atima_fl.core.contracts import AttackContext
from atima_fl.engine.attacks import knowledge_ids, prepare_training, poison_update
from atima_fl.engine.models import attackable_indices, train
from atima_fl.engine.storage import raw_path, write_raw, read_raw


def train_local(config, run, client, round_id, before, data, device):
    original = data.shard(client)
    context = AttackContext(config, client, round_id)
    batch = prepare_training(original.x, original.y, context)
    started = time.perf_counter()
    local = train(before, batch.x, batch.y, config, client, round_id, device)
    registry = config.registry()
    params = registry.parameters("attack", config.attack, config.attack_params)
    metadata = {
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
        "local_update_is_clean_counterfactual": config.attack == "none",
        "local_reference_scope": "local training conditional on incoming global; attacked runs are not paired-clean counterfactuals",
        **batch.notes,
    }
    metadata["local_training_data_altered"] = (
        len(batch.y) != len(original.y)
        or not np.array_equal(batch.x[: len(original.y)], original.x)
        or not np.array_equal(batch.y[: len(original.y)], original.y)
    )
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


def submit_local(config, run, client, round_id, before, counts):
    local, metadata, _ = read_raw(raw_path(run, round_id, client))
    context = AttackContext(
        config,
        client,
        round_id,
        before,
        local,
        counts=counts,
        attackable_indices=attackable_indices(config),
    )
    context.raw_by_client = {
        cid: read_raw(raw_path(run, round_id, cid))[0] for cid in knowledge_ids(context)
    }
    submitted, attack_notes = poison_update(context)
    prepared_applied = metadata.get("attack_applied", False)
    metadata.update(attack_notes)
    metadata["attack_applied"] = prepared_applied or attack_notes.get("attack_applied", False)
    metadata["submitted_differs_from_local"] = any(
        not np.array_equal(a, b) for a, b in zip(submitted, local)
    )
    return submitted, metadata
