"""Per-client, per-round telemetry: one row for every logical client.

Why this file exists: ``final_metrics.json`` keeps aggregates (mean/max update
norm over clients), which cannot answer "how strong was *the attacker's* update"
and therefore cannot establish whether two arms were compared at equal strength.
The per-client series is written here, next to the aggregates, one row per
logical client per round, including the compromised one.

Additive only: nothing in this module is read by the training loop, so the
aggregated metrics of a run are produced by the same code path as before.
"""

from pathlib import Path

from atima_fl.engine.storage import atomic_json

SCHEMA = "atima_fl.client_telemetry/1"
SCOPE = "simulated_logical_clients_server_audit"

# Attack-specific evidence, copied only when present (LCG reports its own budget
# and target-class losses; other attacks report a subset or a reason).
ATTACK_FIELDS = (
    "attack",
    "reason",
    "target_class",
    "target_support",
    "used_target_examples",
    "gradient_l2",
    "local_delta_l2",
    "added_perturbation_l2_budget",
    "local_target_loss_before",
    "local_target_loss_after",
    "objective",
    "knowledge",
    "count_spoofed",
)


def _finite(value):
    """Float or None: telemetry never carries NaN/inf into JSON."""
    if value is None:
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def client_row(client_id, metadata, samples_claimed, update_l2, participated):
    """One client's row for one round.

    ``update_l2`` is the norm of the update actually **submitted** (not the
    clean local delta), measured by the server from the arrays it received.
    """
    attack = {
        key: metadata[key] for key in ATTACK_FIELDS if key in metadata and key != "attack"
    }
    return {
        "client": int(client_id),
        "participated": bool(participated),
        "is_malicious": bool(metadata.get("is_malicious", False)),
        "attack_applied": bool(metadata.get("attack_applied", False)),
        "attack": str(metadata.get("attack", "none")),
        "samples_actual": int(metadata.get("original_samples", 0)),
        "samples_claimed": int(samples_claimed),
        "trained_samples": int(metadata.get("trained_samples", 0)),
        "poisoned_labels": int(metadata.get("poisoned_labels", 0)),
        "local_training_data_altered": bool(metadata.get("local_training_data_altered", False)),
        "update_l2": _finite(update_l2),
        "local_loss": _finite(metadata.get("local_loss")),
        "local_accuracy": _finite(metadata.get("local_accuracy")),
        "local_macro_f1": _finite(metadata.get("local_macro_f1")),
        "local_metrics_split": metadata.get("local_metrics_split"),
        "attack_telemetry": attack,
    }


def round_entry(round_id, rows):
    return {"round": int(round_id), "clients": list(rows)}


def write(run, rounds, clients):
    """Write the whole series atomically, next to the aggregates."""
    atomic_json(
        Path(run) / "client_telemetry.json",
        {"schema": SCHEMA, "scope": SCOPE, "clients": int(clients), "rounds": list(rounds)},
    )
