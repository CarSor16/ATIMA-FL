"""FedAvg count manipulation: a compromised client overstates its sample mass.

This attack controls a *protocol field*, not the local model update or dataset.
The trusted ground truth remains metadata["original_samples"] in simulation.
"""
from atima_fl.core.contracts import Component


def report_count(original, context):
    multiplier = context.config.parameters("attack")["count_multiplier"]
    reported = original * multiplier
    if type(original) is not int or original <= 0 or reported > 2**31 - 1:
        raise ValueError("Invalid original/reported sample count")
    return reported


PLUGIN = Component(
    "sample_weight_hijack", "attack", "FedAvg sample-weight hijacking",
    "Compromised clients overreport their sample count to increase their FedAvg mass; "
    "the local model and data are left intact.",
    {"count_multiplier": {"type": "integer", "default": 3, "minimum": 2, "maximum": 20}},
    {"report_count": report_count},
    threats=("protocol_integrity", "sample_mass_spoofing"),
    limitations="Works only if the aggregator trusts unverified client counts. "
                "Simulates authenticated compromised clients, not forged identities. "
                "Metadata includes actual and reported counts for audit; not a stealth claim.",
)
