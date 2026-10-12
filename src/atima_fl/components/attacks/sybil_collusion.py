"""Model-update identity collusion across explicitly compromised logical clients."""
import numpy as np
from atima_fl.core.contracts import Component

def validate(config, params):
    if len(config.malicious_clients) < 2:
        raise ValueError("Sybil collusion needs at least two malicious logical identities")

def knowledge(context):
    return list(context.config.malicious_clients)

def transform(context):
    leader = min(context.config.malicious_clients)
    if leader not in context.raw_by_client:
        raise ValueError("Colluding reference update not available")
    copy = context.raw_by_client[leader]
    if len(copy) != len(context.local_arrays):
        raise ValueError("Colluding update shape mismatch")
    return [v.copy() for v in copy], {
        "attack_applied": any(not np.array_equal(v, own) for v, own in zip(copy, context.local_arrays)),
        "collusion_leader": leader, "colluding_ids": list(context.config.malicious_clients),
        "scope": "existing malicious logical IDs; does not forge authentication identities"}

PLUGIN = Component(
    "sybil_collusion", "attack", "Sybil-style update collusion",
    "Compromised logical clients submit a shared leader model update.",
    hooks={"validate": validate, "knowledge": knowledge, "transform": transform},
    references=("https://arxiv.org/abs/1808.04866",),
    threats=("sybil_collusion", "byzantine_update"),
    limitations="Simulates coordinated existing clients, not account creation or authentication bypass.",
)
