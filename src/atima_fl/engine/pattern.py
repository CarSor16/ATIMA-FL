"""Pattern analysis for per-round validation histories: per-class signals, damage shape, latency.

Why this module exists. `engine.analysis.compare` answers "how much worse is the attacked run at
the end", and it needs `trajectory.h5` plus a verified clean/attack pair. The questions we actually
ask during a campaign need three other things, none of which requires the HDF5 file:

1. **Per-class signals round by round** — recall per class, benign flow into each attack class, and
   intrusions predicted as benign. These are read from `validation_history.json`, which every run
   writes, including the partial ones.
2. **Shape of the damage** — is a class spared? does the model cycle between degenerate states
   (everything benign, then one class absorbing every benign) instead of staying uniformly broken?
3. **Latency and noise** — when does a signal leave the clean baseline, and how large is that
   baseline's noise when measured on the statistic actually compared (a window mean, not a single
   round)? A threshold built on the wrong denominator reports a delay that is an artefact.

The gate is the same idea used in the campaign notes: the stored `macro_f1` and `per_class` recalls
are recomputed from the confusion matrix, and nothing is returned if they disagree.

Conventions, fixed and checked: rows of the confusion matrix are the true class, columns the
predicted class, in the order of `per_class` (benign, dos, infog, inject, malware).
"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

CLASS_ORDER = ("benign", "dos", "infog", "inject", "malware")
TOLERANCE = 1e-9


def _history_path(target):
    path = Path(target)
    if path.is_dir():
        path = path / "validation_history.json"
    if not path.is_file():
        raise FileNotFoundError(f"No validation history at {path}")
    return path


def load_history(target):
    """Read a run directory or a history file; returns the list of round records."""
    return json.loads(_history_path(target).read_text(encoding="utf-8"))


def _classes(record):
    per_class = record.get("per_class") or {}
    return tuple(per_class) if per_class else CLASS_ORDER


def _matrix(record):
    matrix = record.get("confusion_matrix")
    if not matrix:
        raise ValueError(f"Round {record.get('round')} has no confusion matrix")
    return matrix


def round_metrics(record):
    """Per-class metrics recomputed from the confusion matrix, plus the row/column margins."""
    classes = _classes(record)
    matrix = _matrix(record)
    totals = [sum(row) for row in matrix]
    predicted = [sum(matrix[r][c] for r in range(len(matrix))) for c in range(len(classes))]
    recall = [(matrix[i][i] / totals[i]) if totals[i] else 0.0 for i in range(len(classes))]
    precision = [
        (matrix[c][c] / predicted[c]) if predicted[c] else 0.0 for c in range(len(classes))
    ]
    f1 = [
        (2 * p * r / (p + r)) if (p + r) else 0.0 for p, r in zip(precision, recall)
    ]
    intrusions = sum(totals[1:])
    benign_row = matrix[0] if totals else []
    return {
        "round": record.get("round"),
        "classes": list(classes),
        "macro_f1": sum(f1) / len(f1),
        "f1": dict(zip(classes, f1)),
        "recall": dict(zip(classes, recall)),
        "benign_to_pct": {
            classes[c]: (100.0 * benign_row[c] / totals[0] if totals[0] else 0.0)
            for c in range(1, len(classes))
        },
        "miss_pct": {
            classes[c]: (100.0 * matrix[c][0] / totals[c] if totals[c] else 0.0)
            for c in range(1, len(classes))
        },
        "miss_total_pct": (
            100.0 * sum(matrix[c][0] for c in range(1, len(classes))) / intrusions
            if intrusions
            else 0.0
        ),
        "samples": record.get("samples"),
    }


def verify(history):
    """Recompute the stored metrics; raise if the file and the matrix disagree.

    Both the macro-F1 and the per-class recalls are checked: a flipped row/column convention would
    keep macro-F1 plausible while changing every recall, so checking only the aggregate would not
    catch it.
    """
    worst_f1 = 0.0
    worst_recall = 0.0
    for record in history:
        derived = round_metrics(record)
        worst_f1 = max(worst_f1, abs(derived["macro_f1"] - record.get("macro_f1", 0.0)))
        stored = record.get("per_class") or {}
        for name, value in stored.items():
            worst_recall = max(worst_recall, abs(derived["recall"][name] - value.get("recall", 0.0)))
    if worst_f1 > TOLERANCE or worst_recall > TOLERANCE:
        raise ValueError(
            "Stored metrics disagree with the confusion matrices "
            f"(macro_f1 {worst_f1:.2e}, recall {worst_recall:.2e})"
        )
    return {"rounds": len(history), "max_macro_f1_gap": worst_f1, "max_recall_gap": worst_recall}


def series(history):
    """Verified per-round series, in round order; gaps remain explicit."""
    if not history:
        raise ValueError("Empty validation history")
    verify(history)
    rows = sorted((round_metrics(record) for record in history), key=lambda row: row["round"])
    rounds = [row["round"] for row in rows]
    if any(type(number) is not int or number < 1 for number in rounds) or len(set(rounds)) != len(rounds):
        raise ValueError("Validation history requires unique positive round IDs")
    if any(row["classes"] != rows[0]["classes"] for row in rows):
        raise ValueError("Class order changes inside validation history")
    return rows


def window(rows, start=41, end=50):
    return [row for row in rows if start <= row["round"] <= end]


def summarize_window(rows, start=41, end=50):
    """Mean of the chosen window: the statistic a paired verdict should be built on."""
    chosen = window(rows, start, end)
    if not chosen:
        raise ValueError(f"No rounds in window {start}-{end}")
    attack = [name for name in chosen[0]["classes"] if name != "benign"]

    def mean(values):
        return float(st.fmean(values)) if values else 0.0

    return {
        "window": [chosen[0]["round"], chosen[-1]["round"]],
        "rounds": len(chosen),
        "macro_f1": mean([row["macro_f1"] for row in chosen]),
        "miss_total_pct": mean([row["miss_total_pct"] for row in chosen]),
        "benign_to_pct": {c: mean([row["benign_to_pct"][c] for row in chosen]) for c in attack},
        "miss_pct": {c: mean([row["miss_pct"][c] for row in chosen]) for c in attack},
        "recall": dict(
            {c: mean([row["recall"][c] for row in chosen]) for c in chosen[0]["classes"]}
        ),
    }


def structure(rows, attack_start=10):
    """Temporal structure of the damage: sustained or episodic.

    A ten-round mean cannot tell a 10% signal present in every round from a 99% signal present in
    one: these counts can. `saturated_rounds` counts rounds with at least `saturation_pct` of the
    intrusions predicted benign (the "benign sink"); `benign_to_rounds` counts rounds above a small
    presence threshold; `modes` lists the classes that ever absorb `mode_pct` of the benign row.
    """
    chosen = [row for row in rows if row["round"] >= attack_start]
    if not chosen:
        return {"rounds": 0}
    attack = [name for name in chosen[0]["classes"] if name != "benign"]
    total = [row["miss_total_pct"] for row in chosen]
    benign_to = {c: [row["benign_to_pct"][c] for row in chosen] for c in attack}

    def count(values, threshold):
        return sum(1 for value in values if value >= threshold)

    mean = float(st.fmean(total))
    deviation = float(st.stdev(total)) if len(total) > 1 else 0.0
    benign_dos = benign_to.get("dos", [])
    return {
        "rounds": len(chosen),
        "saturated_rounds": count(total, 90.0),
        "max_miss_total_pct": max(total),
        "mean_miss_total_pct": mean,
        "benign_to_rounds": {c: count(benign_to[c], 1.0) for c in attack},
        "benign_to_saturated_rounds": {c: count(benign_to[c], 20.0) for c in attack},
        "max_benign_to_pct": {c: max(benign_to[c]) for c in attack},
        "modes": sorted(c for c in attack if max(benign_to[c]) >= 20.0),
        "cv_benign_to_dos": (
            (float(st.stdev(benign_dos)) / float(st.fmean(benign_dos)))
            if benign_dos and float(st.fmean(benign_dos)) > 0.0 and len(benign_dos) > 1
            else None
        ),
        "mean_cost_std_pct": deviation,
    }


def noise(clean_histories, start=41, end=50):
    """Noise of the comparison actually made: the spread of window means, not of single rounds.

    `within_window` is the round-to-round jitter inside one window (mean over runs);
    `across_runs` is the spread of the window means between runs. A threshold placed on the second
    quantifies how surprising a shift of the window mean is; a threshold placed on the first (or on
    all rounds pooled, which also carries the burn-in) is systematically wider.
    """
    summaries = [summarize_window(series(history), start, end) for history in clean_histories]
    if len(summaries) < 2:
        raise ValueError("At least two clean runs are needed to measure across-run noise")
    rows = [series(history) for history in clean_histories]

    def across(values):
        return float(st.stdev(values))

    def within(fn):
        spreads = []
        for run in rows:
            values = [fn(row) for row in window(run, start, end)]
            if len(values) > 1:
                spreads.append(float(st.stdev(values)))
        return float(st.fmean(spreads)) if spreads else 0.0

    def window_mean(fn):
        return [float(st.fmean([fn(row) for row in window(run, start, end)])) for run in rows]

    signals = {
        "macro_f1": (lambda row: row["macro_f1"], lambda row: 100.0 * row["macro_f1"]),
        "miss_total_pct": (lambda row: row["miss_total_pct"], lambda row: row["miss_total_pct"]),
        "benign_to_dos_pct": (
            lambda row: row["benign_to_pct"].get("dos", 0.0),
            lambda row: row["benign_to_pct"].get("dos", 0.0),
        ),
    }
    out = {}
    for name, (raw, percent) in signals.items():
        across_values = window_mean(raw)
        out[name] = {
            "mean": float(st.fmean(across_values)),
            "across_runs": across(across_values),
            "within_window": within(raw),
            "k_min_effect": 2.8 * across(across_values),
            "per_round_scale": across(window_mean(percent)),
        }
    return {"window": [start, end], "runs": len(clean_histories), "signals": out}


def minimum_detectable(sd, arms=1, k=2.8):
    """Smallest difference visible against a known reference: k = z(0.975) + z(0.80)."""
    return k * sd / math.sqrt(arms)


def rolling(values, size):
    out = []
    for index in range(len(values)):
        chunk = values[max(0, index - size + 1): index + 1]
        out.append(float(st.fmean(chunk)) if len(chunk) >= size else None)
    return out


def _rolling_by_round(rows, fn, size):
    """Use actual round IDs and only complete contiguous windows."""
    values = {row["round"]: fn(row) for row in rows}
    return {
        number: float(st.fmean(values[r] for r in range(number - size + 1, number + 1)))
        for number in values
        if all(r in values for r in range(number - size + 1, number + 1))
    }


def _reference(clean_histories, size=10, floor_pp=0.05):
    """Reference for actual round IDs, requiring a full window in each clean run."""
    if not clean_histories:
        raise ValueError("At least one clean history is required")
    runs = [series(history) for history in clean_histories]
    if any(run[0]["classes"] != runs[0][0]["classes"] for run in runs):
        raise ValueError("Clean histories have different class orders")
    reference = {}
    for name, fn in (
        ("macro_f1", lambda row: 100.0 * row["macro_f1"]),
        ("miss_total_pct", lambda row: row["miss_total_pct"]),
        ("benign_to_dos_pct", lambda row: row["benign_to_pct"].get("dos", 0.0)),
    ):
        rolled = [_rolling_by_round(run, fn, size) for run in runs]
        common = set.intersection(*(set(run) for run in rolled))
        reference[name] = {}
        for number in sorted(common):
            values = [run[number] for run in rolled]
            reference[name][number] = (
                float(st.fmean(values)),
                max(float(st.stdev(values)), floor_pp) if len(values) > 1 else floor_pp,
            )
    return reference


def detect(history, clean_histories, window=10, threshold=3.0, confirm=2, attack_start=10):
    """Find consecutive threshold crossings against actual round-matched clean windows.

    Missing observations are not treated as clean evidence or consecutive rounds.
    A final isolated crossing cannot satisfy a multi-round confirmation rule.
    """
    if type(window) is not int or window < 1 or type(confirm) is not int or confirm < 1:
        raise ValueError("Window and confirmation must be positive integers")
    if not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("Threshold must be finite and positive")
    rows = series(history)
    clean_rows = [series(clean) for clean in clean_histories]
    if any(clean[0]["classes"] != rows[0]["classes"] for clean in clean_rows):
        raise ValueError("Clean and attacked histories have different class orders")
    reference = _reference(clean_histories, window)
    out = {}
    for name, fn in (
        ("macro_f1", lambda row: 100.0 * row["macro_f1"]),
        ("miss_total_pct", lambda row: row["miss_total_pct"]),
        ("benign_to_dos_pct", lambda row: row["benign_to_pct"].get("dos", 0.0)),
    ):
        values = _rolling_by_round(rows, fn, window)
        sign = -1.0 if name == "macro_f1" else 1.0
        deviations = {
            number: sign * (value - reference[name][number][0]) / reference[name][number][1]
            for number, value in values.items() if number in reference[name]
        }
        above = {number for number, value in deviations.items()
                 if number >= attack_start and value > threshold}
        first = next((number for number in sorted(above)
                      if all(r in above for r in range(number, number + confirm))), None)
        longest = streak = 0
        previous = None
        for number in sorted(above):
            streak = streak + 1 if previous is not None and number == previous + 1 else 1
            longest = max(longest, streak)
            previous = number
        out[name] = {
            "first_round": first,
            "rounds_above": len(above),
            "rounds_attack": sum(row["round"] >= attack_start for row in rows),
            "rounds_evaluable": sum(number >= attack_start for number in deviations),
            "longest_run": longest,
            "max_deviation": max(deviations.values(), default=0.0),
        }
    return out


def paired_verdict(clean, attacked, start=41, end=50, attack_start=10):
    """Everything a paired claim needs, without trajectory.h5 and without a pair_id check."""
    clean_rows = series(clean)
    attacked_rows = series(attacked)
    if not clean_rows or not attacked_rows:
        raise ValueError("Empty history")
    base = summarize_window(clean_rows, start, end)
    attack = summarize_window(attacked_rows, start, end)
    classes = [name for name in base["recall"] if name != "benign"]
    losses = {c: 100.0 * (base["recall"][c] - attack["recall"][c]) for c in classes}
    return {
        "window": [start, end],
        "clean_macro_f1": base["macro_f1"],
        "attacked_macro_f1": attack["macro_f1"],
        "delta_macro_f1": attack["macro_f1"] - base["macro_f1"],
        "clean_miss_total_pct": base["miss_total_pct"],
        "attacked_miss_total_pct": attack["miss_total_pct"],
        "recall_loss_pp": losses,
        "total_loss_pp": sum(max(0.0, value) for value in losses.values()),
        "clean_miss_pct": base["miss_pct"],
        "attacked_miss_pct": attack["miss_pct"],
        "clean_benign_to_pct": base["benign_to_pct"],
        "attacked_benign_to_pct": attack["benign_to_pct"],
        "attacked_structure": structure(attacked_rows, attack_start),
        "clean_structure": structure(clean_rows, attack_start),
    }


def report(run, clean=None, start=41, end=50, attack_start=10):
    """One call that returns the whole pattern picture for a run directory."""
    history = load_history(run)
    rows = series(history)
    out = {
        "run": str(Path(run)),
        "gate": verify(history),
        "rounds": len(rows),
        "window": summarize_window(rows, start, end),
        "structure": structure(rows, attack_start),
        "last_round": {k: v for k, v in rows[-1].items() if k not in ("classes", "f1")},
    }
    if clean is not None:
        out["paired"] = paired_verdict(load_history(clean), history, start, end, attack_start)
    return out
