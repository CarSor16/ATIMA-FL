"""Selective paired metrics and plots; no training and no routine log export."""

from pathlib import Path
import hashlib
import json
import h5py
import numpy as np
from atima_fl.core.numerics import trajectory_metrics
from .storage import atomic_json


def compare(clean, attacked, destination):
    clean, attacked, destination = map(Path, (clean, attacked, destination))
    cm = json.loads((clean / "manifest.json").read_text())
    am = json.loads((attacked / "manifest.json").read_text())
    if cm["status"] != "complete" or am["status"] != "complete" or cm["pair_id"] != am["pair_id"]:
        raise ValueError("Only complete matched runs can support paired conclusions")
    if cm["config"]["attack"] != "none" or am["config"]["attack"] == "none":
        raise ValueError("Expected a clean/attacked pair")
    for key in ("source_identity", "runtime", "last_valid_round"):
        if cm[key] != am[key]:
            raise ValueError(f"Pair mismatch: {key}")
    rows = []

    def weights(group):
        return [group[key][...] for key in sorted(group)]

    with h5py.File(clean / "trajectory.h5") as c, h5py.File(attacked / "trajectory.h5") as a:
        cp, ap = weights(c["initial"]), weights(a["initial"])
        if len(cp) != len(ap) or any(not np.array_equal(x, y) for x, y in zip(cp, ap)):
            raise ValueError("Pair initial weights differ")
        initial_hash = hashlib.sha256(
            b"".join(str((w.shape, str(w.dtype))).encode() + w.tobytes() for w in cp)
        ).hexdigest()
        for r in range(1, min(cm["last_valid_round"], am["last_valid_round"]) + 1):
            key = f"rounds/round_{r:04d}"
            cg, ag = c[key], a[key]
            cv, av = (
                json.loads(cg.attrs["validation_json"]),
                json.loads(ag.attrs["validation_json"]),
            )
            cw, aw = weights(cg["global_after"]), weights(ag["global_after"])
            cr, ar = np.asarray(cv["recall"]), np.asarray(av["recall"])
            rows.append(
                {
                    "round": r,
                    **trajectory_metrics(aw, cw, ap, cp),
                    "clean_macro_f1": cv["macro_f1"],
                    "attacked_macro_f1": av["macro_f1"],
                    "delta_macro_f1": av["macro_f1"] - cv["macro_f1"],
                    "delta_accuracy": av["accuracy"] - cv["accuracy"],
                    "delta_recall": (ar - cr).tolist(),
                    "relative_recall_degradation": [
                        None if x == 0 else float((x - y) / x) for x, y in zip(cr, ar)
                    ],
                }
            )
            rows[-1]["clients"] = {}
            for cid in range(cm["config"]["clients"]):
                group = f"clients/client_{cid:02d}"
                local = weights(ag[f"{group}/local_update"])
                sent = weights(ag[f"{group}/submitted_update"])
                clean_local = weights(cg[f"{group}/local_update"])
                lv, sv, cvv = (
                    np.concatenate([v.astype(np.float64).ravel() for v in arrays])
                    for arrays in (local, sent, clean_local)
                )
                rows[-1]["clients"][str(cid)] = {
                    "local_update_l2": float(np.linalg.norm(lv)),
                    "submitted_update_l2": float(np.linalg.norm(sv)),
                    "attack_transform_l2": float(np.linalg.norm(sv - lv)),
                    "local_vs_paired_clean_l2": float(np.linalg.norm(lv - cvv)),
                    "clean_reference_scope": "paired clean trajectory; after divergence, incoming global differs",
                }
            cp, ap = cw, aw
    # AUD: trapezoidal integral of positive clean-attacked macro-F1 gaps vs round.
    gaps = np.maximum(0, [-v["delta_macro_f1"] for v in rows])
    summary = {
        "pair_id": cm["pair_id"],
        "attack": am["config"]["attack"],
        "rounds": rows,
        "aud_positive_macro_f1_gap": float(np.trapezoid(gaps, x=[v["round"] for v in rows])),
        "aud_definition": "trapezoidal integral of max(0,F1_clean-F1_attack) against round; single-round area=0",
    }
    cf = json.loads((clean / "final_metrics.json").read_text())
    af = json.loads((attacked / "final_metrics.json").read_text())
    condition = dict(am["config"])
    for key in ("name", "seed", "dataset_root", "output_root", "paired_clean", "plugin_directory"):
        condition.pop(key, None)
    condition["dataset_hashes"] = am["dataset_audit"]["hashes"]
    condition["source_identity"] = am["source_identity"]
    condition["attack_source"] = am["attack_source"]
    summary = {
        "summary": {
            "seed": am["config"]["seed"],
            "status": "complete",
            "condition_id": hashlib.sha256(
                json.dumps(condition, sort_keys=True).encode()
            ).hexdigest(),
            "delta_test_macro_f1": af["test"]["macro_f1"] - cf["test"]["macro_f1"],
            "clean_test": cf["test"],
            "attacked_test": af["test"],
            "aud_positive_macro_f1_gap": summary["aud_positive_macro_f1_gap"],
            "aud_definition": summary["aud_definition"],
            "pair_id": cm["pair_id"],
            "attack": am["config"]["attack"],
            "clean_attack_metrics": cf.get("attack_metrics"),
            "attacked_attack_metrics": af.get("attack_metrics"),
        },
        "protocol": {
            "condition": condition,
            "runtime": am["runtime"],
            "initial_weights_sha256": initial_hash,
        },
        "rounds": rows,
    }
    destination.mkdir(parents=True, exist_ok=False)
    atomic_json(destination / "comparison.json", summary)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = [v["round"] for v in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(x, [v["clean_macro_f1"] for v in rows], label="Clean")
    axes[0].plot(x, [v["attacked_macro_f1"] for v in rows], label=am["config"]["attack"])
    axes[0].set(ylabel="Validation macro-F1", xlabel="Round")
    axes[0].legend()
    axes[1].plot(x, [v["weight_l2_normalized"] for v in rows])
    axes[1].set(ylabel="Normalized global weight L2 distance", xlabel="Round")
    fig.tight_layout()
    fig.savefig(destination / "paired_trajectory.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    for cid, name in enumerate(cm["dataset_audit"]["classes"]):
        ax.plot(x, [v["delta_recall"][cid] for v in rows], label=name)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set(xlabel="Round", ylabel="Recall attack - clean")
    ax.legend()
    fig.tight_layout()
    fig.savefig(destination / "per_class_recall.png", dpi=180)
    plt.close(fig)
    return summary
