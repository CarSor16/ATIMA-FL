"""Client non-contribution: the submitted trainable update is identically zero."""
import numpy as np
from atima_fl.core.contracts import Component

def transform(context):
    equal = all(np.array_equal(a, b) for a, b in zip(context.local_arrays, context.global_arrays))
    return [a.copy() for a in context.global_arrays], {
        "attack_applied": not equal, "free_rider_zero_update": True,
        "mechanism": "submitted trainable delta set to zero despite completed local training"}

PLUGIN = Component(
    "free_rider", "attack", "Free rider (zero contribution)",
    "Client submits a zero trainable delta while claiming participation.",
    hooks={"transform": transform},
    references=("https://arxiv.org/abs/1911.12560",),
    threats=("free_riding", "protocol_integrity"),
    limitations="Benchmark zero-delta free riding; realistic stealthy free-rider strategies require separate verification.",
)
