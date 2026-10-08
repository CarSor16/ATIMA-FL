"""Compare two complete clean/attack pairs; reject uncontrolled protocol changes."""

from copy import deepcopy
from pathlib import Path
import json
import numpy as np
from .storage import atomic_json


def comparable_protocol(comparison):
    protocol = deepcopy(comparison["protocol"])
    condition = protocol["condition"]
    for key in ("defenses", "aggregation", "aggregation_params"):
        condition.pop(key)
    condition["source_identity"] = {
        k: v
        for k, v in condition["source_identity"].items()
        if not k.startswith(("component/defense/", "component/aggregator/"))
    }
    protocol["seed"] = comparison["summary"]["seed"]
    protocol["round_ids"] = [r["round"] for r in comparison["rounds"]]
    return protocol


def compare_defenses(unprotected, protected, destination):
    u, p = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (unprotected, protected)]
    if any(v["summary"]["status"] != "complete" or not v["rounds"] for v in (u, p)):
        raise ValueError("Defense comparison requires complete nonempty paired analyses")
    if comparable_protocol(u) != comparable_protocol(p):
        raise ValueError(
            "Defense comparison mismatch: seed, horizon, data, initialization, runtime or non-defense protocol"
        )
    uc, pc = [v["protocol"]["condition"] for v in (u, p)]
    if uc["defenses"] or uc["aggregation"] != "fedavg":
        raise ValueError("Unprotected pair must use FedAvg without defense stages")
    if not pc["defenses"] and pc["aggregation"] == "fedavg":
        raise ValueError("Protected pair needs a defense stage or a robust aggregator")
    us, ps = u["summary"], p["summary"]
    asr_reduction = target_rate_change = None
    ua, pa = us.get("attacked_attack_metrics"), ps.get("attacked_attack_metrics")
    if bool(ua) != bool(pa):
        raise ValueError("Mismatched attack-specific evaluation")
    if ua and pa:
        if (ua.get("target"), ua.get("non_target_samples")) != (
            pa.get("target"),
            pa.get("non_target_samples"),
        ):
            raise ValueError("Backdoor target or eligible population mismatch")
        if ua.get("non_target_samples", 0) > 0:
            vals = [
                m.get(k)
                for m in (ua, pa)
                for k in ("asr_all_non_target", "clean_target_rate_on_non_target")
            ]
            if any(v is None or not np.isfinite(v) or not 0 <= v <= 1 for v in vals):
                raise ValueError("Invalid backdoor rates")
            asr_reduction = ua["asr_all_non_target"] - pa["asr_all_non_target"]
            target_rate_change = (
                pa["clean_target_rate_on_non_target"] - ua["clean_target_rate_on_non_target"]
            )
    recovery = ps["attacked_test"]["macro_f1"] - us["attacked_test"]["macro_f1"]
    utility = ps["clean_test"]["macro_f1"] - us["clean_test"]["macro_f1"]
    result = {
        "seed": ps["seed"],
        "status": "complete",
        "attacked_test_macro_f1_recovery": recovery,
        "clean_test_macro_f1_change": utility,
        "attack_damage_reduction": recovery - utility,
        "backdoor_asr_reduction": asr_reduction,
        "untriggered_target_rate_change": target_rate_change,
        "aud_reduction": us["aud_positive_macro_f1_gap"] - ps["aud_positive_macro_f1_gap"],
        "attacked_test_recall_change": (
            np.asarray(ps["attacked_test"]["recall"]) - np.asarray(us["attacked_test"]["recall"])
        ).tolist(),
        "clean_test_recall_change": (
            np.asarray(ps["clean_test"]["recall"]) - np.asarray(us["clean_test"]["recall"])
        ).tolist(),
        "unprotected": us,
        "protected": ps,
        "protocol": comparable_protocol(p),
        "protection": {k: pc[k] for k in ("aggregation", "aggregation_params", "defenses")},
        "protection_sources": {
            k: v
            for k, v in pc["source_identity"].items()
            if k.startswith(("component/defense/", "component/aggregator/"))
        },
        "reference_sources": {
            k: v
            for k, v in uc["source_identity"].items()
            if k.startswith(("component/defense/", "component/aggregator/"))
        },
        "interpretation": "Positive recovery improves attacked F1; negative clean change is utility loss. One matched seed is diagnostic, not statistical evidence.",
    }
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    atomic_json(destination / "defense_comparison.json", result)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for pair, label in ((u, "Unprotected"), (p, "Protected")):
        for key, style in (("clean_macro_f1", "--"), ("attacked_macro_f1", "-")):
            axes[0].plot(
                [r["round"] for r in pair["rounds"]],
                [r[key] for r in pair["rounds"]],
                style,
                label=label + " " + key.split("_")[0],
            )
    axes[0].set(xlabel="Round", ylabel="Validation macro-F1")
    axes[0].legend(fontsize=8)
    axes[1].bar(
        ["Attacked recovery", "Clean utility change", "Damage-adjusted gain"],
        [recovery, utility, recovery - utility],
    )
    axes[1].axhline(0, color="black", linewidth=0.6)
    axes[1].set(ylabel="Test macro-F1 difference")
    axes[1].tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    fig.savefig(destination / "defense_effect.png", dpi=180)
    plt.close(fig)
    return result
