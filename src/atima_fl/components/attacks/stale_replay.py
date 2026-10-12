"""Replay an earlier LOCAL model snapshot as the submitted update."""
from pathlib import Path
import numpy as np
from atima_fl.core.contracts import Component

def validate(config, params):
    if config.attack_start <= params["lag_rounds"]:
        raise ValueError("Stale replay requires an earlier completed local round")

def transform(context):
    # Keep the lightweight GUI/catalog independent of optional training deps.
    from atima_fl.engine.storage import raw_path, read_raw
    lag = context.config.parameters("attack")["lag_rounds"]
    location = getattr(context, "run_dir", None)
    if location is None:
        raise ValueError("Replay requires an audited run directory")
    path = raw_path(Path(location), context.round_id - lag, context.client)
    if not path.is_file():
        raise ValueError("Previous local snapshot unavailable for replay")
    previous, metadata, _ = read_raw(path)
    if metadata.get("client") != context.client or metadata.get("round") != context.round_id - lag:
        raise ValueError("Replay snapshot identity mismatch")
    if len(previous) != len(context.global_arrays) or any(
        a.shape != b.shape for a, b in zip(previous, context.global_arrays)
    ):
        raise ValueError("Replay snapshot shape mismatch")
    return [v.copy() for v in previous], {
        "attack_applied": any(not np.array_equal(a, b) for a, b in zip(previous, context.local_arrays)),
        "replay_source_round": context.round_id - lag,
        "replay_lag": lag,
        "replay_type": "previous local model snapshot, not a reconstructed old delta"}

PLUGIN = Component(
    "stale_replay", "attack", "Stale model replay",
    "Reuses a previous local model snapshot in place of the current client contribution.",
    {"lag_rounds": {"type": "integer", "default": 1, "minimum": 1}},
    {"validate": validate, "transform": transform},
    threats=("stale_update", "protocol_integrity"),
    limitations="Models stale client submissions, not a physical delayed-network attack; audited prior snapshots required.",
)
