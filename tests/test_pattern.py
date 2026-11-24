"""Tests for the pattern analysis: the gate, the damage shape, the noise and the latency.

The records are built by an independent computation in this file, so `pattern.verify` is checking a
second implementation, not itself.
"""

import json
import math

import pytest

from atima_fl.engine import pattern


CLASSES = list(pattern.CLASS_ORDER)


def _per_class(matrix):
    """Per-class recall and F1 computed here, independently of the module under test."""
    totals = [sum(row) for row in matrix]
    predicted = [sum(matrix[r][c] for r in range(len(matrix))) for c in range(len(CLASSES))]
    out = {}
    for index, name in enumerate(CLASSES):
        recall = matrix[index][index] / totals[index] if totals[index] else 0.0
        precision = matrix[index][index] / predicted[index] if predicted[index] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[name] = {"precision": precision, "recall": recall, "f1-score": f1, "support": totals[index]}
    return out


def _record(round_id, matrix):
    per_class = _per_class(matrix)
    return {
        "round": round_id,
        "confusion_matrix": matrix,
        "per_class": per_class,
        "macro_f1": sum(item["f1-score"] for item in per_class.values()) / len(CLASSES),
        "samples": sum(sum(row) for row in matrix),
    }


def _detected_rows():
    """One row per attack class, each detected correctly (column = own class)."""
    return [[0 if target != index else 100 for target in range(5)] for index in range(1, 5)]


def _sink_rows():
    """Every attack sample predicted benign: the benign sink."""
    return [[100, 0, 0, 0, 0] for _ in range(4)]


def _episodic(rounds=50, burst=(43, 44, 45)):
    """Attack samples fall into the benign sink in three rounds, nothing otherwise."""
    history = []
    for round_id in range(1, rounds + 1):
        benign = [1000, 0, 0, 0, 0]
        attack = _sink_rows() if round_id in burst else _detected_rows()
        history.append(_record(round_id, [benign] + attack))
    return history


def _sustained(rounds=50, benign_to_dos=10):
    history = []
    for round_id in range(1, rounds + 1):
        benign = [1000 - benign_to_dos, benign_to_dos, 0, 0, 0]
        history.append(_record(round_id, [benign] + _detected_rows()))
    return history


def _clean(rounds=50, benign_to_dos=1):
    history = []
    for round_id in range(1, rounds + 1):
        benign = [1000 - benign_to_dos, benign_to_dos, 0, 0, 0]
        history.append(_record(round_id, [benign] + _detected_rows()))
    return history


def test_round_metrics_are_recomputed_from_the_matrix():
    matrix = [[80, 20, 0, 0, 0], [0, 60, 40, 0, 0], [0, 0, 50, 50, 0], [0, 0, 0, 90, 10], [0, 0, 0, 0, 100]]
    derived = pattern.round_metrics(_record(1, matrix))
    assert derived["recall"]["benign"] == pytest.approx(0.8)
    assert derived["recall"]["dos"] == pytest.approx(0.6)
    assert derived["benign_to_pct"]["dos"] == pytest.approx(20.0)
    assert derived["miss_pct"]["infog"] == pytest.approx(0.0)


def test_gate_rejects_a_history_whose_numbers_do_not_match():
    history = _clean(rounds=3)
    pattern.verify(history)  # consistent by construction
    history[1]["macro_f1"] += 0.01
    with pytest.raises(ValueError, match="disagree"):
        pattern.verify(history)


def test_gate_rejects_flipped_recalls_even_when_macro_f1_matches():
    """A row/column mix-up keeps the aggregate plausible; the recall check is what catches it."""
    history = _clean(rounds=2)
    name = "dos"
    history[0]["per_class"][name]["recall"] += 0.2
    with pytest.raises(ValueError, match="disagree"):
        pattern.verify(history)


def test_structure_separates_episodic_from_sustained():
    episodic = pattern.structure(pattern.series(_episodic()))
    sustained = pattern.structure(pattern.series(_sustained()))
    assert episodic["saturated_rounds"] == 3
    assert sustained["saturated_rounds"] == 0
    # the sustained run has the signal in every round, the episodic one only where it burns
    assert sustained["benign_to_rounds"]["dos"] == sustained["rounds"]
    assert episodic["benign_to_rounds"]["dos"] == 0
    assert sustained["modes"] == []
    assert episodic["cv_benign_to_dos"] is None  # mean is zero: no relative spread to report


def test_window_summary_and_paired_verdict():
    clean = pattern.series(_clean())
    attacked = pattern.series(_episodic())
    verdict = pattern.paired_verdict(_clean(), _episodic())
    assert verdict["delta_macro_f1"] < 0
    assert verdict["attacked_miss_total_pct"] > verdict["clean_miss_total_pct"]
    assert verdict["total_loss_pp"] > 0
    # the window covers rounds 41-50, which contain the burst
    assert verdict["attacked_structure"]["saturated_rounds"] == 3
    assert pattern.summarize_window(clean)["rounds"] == 10
    assert pattern.summarize_window(attacked)["miss_total_pct"] > 0


def test_noise_grows_with_between_run_spread():
    tight = [_clean(benign_to_dos=1) for _ in range(3)]
    loose = [_clean(benign_to_dos=value) for value in (0.5, 3.0, 6.0)]
    tight_noise = pattern.noise(tight)["signals"]["benign_to_dos_pct"]
    loose_noise = pattern.noise(loose)["signals"]["benign_to_dos_pct"]
    assert loose_noise["across_runs"] > tight_noise["across_runs"]
    assert loose_noise["k_min_effect"] == pytest.approx(2.8 * loose_noise["across_runs"])
    assert pattern.minimum_detectable(0.01, arms=4) < pattern.minimum_detectable(0.01, arms=1)


def test_noise_needs_two_clean_runs():
    with pytest.raises(ValueError, match="two clean runs"):
        pattern.noise([_clean()])


def test_detect_finds_the_onset_and_stays_silent_on_a_clean_run():
    clean_runs = [_clean() for _ in range(3)]
    detected = pattern.detect(_episodic(), clean_runs)
    # the burst starts at round 43; the rolling mean needs the round to enter the window
    assert detected["miss_total_pct"]["first_round"] == 43
    # the rolling mean keeps the three-round burst for the rest of the window: 43..50
    assert detected["miss_total_pct"]["rounds_above"] == 8
    assert detected["miss_total_pct"]["longest_run"] == 8
    silent = pattern.detect(_clean(), clean_runs)
    assert silent["miss_total_pct"]["first_round"] is None


def test_rolling_window_is_none_until_full():
    values = pattern.rolling([1.0, 2.0, 3.0, 4.0], 3)
    assert values[:2] == [None, None]
    assert values[2] == pytest.approx(2.0)
    assert values[3] == pytest.approx(3.0)


def test_report_reads_a_run_directory(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "validation_history.json").write_text(json.dumps(_episodic()), encoding="utf-8")
    data = pattern.report(run)
    assert data["gate"]["rounds"] == 50
    assert data["structure"]["saturated_rounds"] == 3
    assert math.isclose(data["window"]["macro_f1"], data["window"]["macro_f1"])
    with pytest.raises(FileNotFoundError):
        pattern.load_history(tmp_path / "missing")


def test_detection_never_confirms_single_trailing_crossing():
    attacked = _episodic(rounds=50, burst=(50,))
    clean = [_clean() for _ in range(3)]
    found = pattern.detect(attacked, clean, window=1, confirm=2)
    assert found["miss_total_pct"]["rounds_above"] == 1
    assert found["miss_total_pct"]["first_round"] is None


def test_detection_aligns_real_rounds_and_never_bridges_missing_round():
    attacked = _episodic(rounds=50, burst=(43, 44, 45))
    attacked = [row for row in attacked if row["round"] != 44]
    clean = [_clean() for _ in range(3)]
    found = pattern.detect(attacked, clean, window=1, confirm=2)
    assert found["miss_total_pct"]["first_round"] is None
    assert found["miss_total_pct"]["longest_run"] == 1
    # Short clean histories cannot cause indexing errors or fabricated evidence.
    partial = pattern.detect(attacked, [_clean(rounds=40)], window=1, confirm=2)
    assert partial["miss_total_pct"]["first_round"] is None
    assert partial["miss_total_pct"]["rounds_evaluable"] == 31


def test_pattern_series_enforces_metric_gate_for_every_consumer():
    history = _clean(rounds=3)
    history[1]["macro_f1"] += 0.1
    with pytest.raises(ValueError, match="disagree"):
        pattern.series(history)
