"""Client-level metric checks for the HyperFL++ branch.

Two properties this pins down:

* the MCC reported for a 5-class confusion matrix is the multiclass MCC
  (identical to ``sklearn.metrics.matthews_corrcoef``), not a binary reduction;
* ``aggregate_personalized`` keeps one confusion matrix per client instead of
  only the pooled one, so a future run can report per-client harm.
"""

import math

import numpy as np
import pytest
from sklearn.metrics import matthews_corrcoef

from atima_fl.engine.hyperfl import aggregate_personalized, multiclass_mcc

CLASSES = ["benign", "dos", "infog", "inject", "malware"]

# Pooled test matrix of arm A (HyperFL++ clean) as stored by the cluster: the
# 139,275-row test set is evaluated by each of the ten client models, so the
# matrix sums 1,392,750 rows. Used as a real, non-synthetic known case.
ARM_A = np.array([
    [798864, 16, 17, 46, 1187],
    [967, 116458, 93213, 10814, 9248],
    [14, 0, 30743, 3910, 23],
    [215, 13, 1399, 31516, 6207],
    [8, 15, 29, 2743, 285085],
])


def labels(matrix):
    y_true = np.repeat(np.arange(matrix.shape[0]), matrix.sum(axis=1))
    y_pred = np.concatenate([np.repeat(np.arange(matrix.shape[1]), row) for row in matrix])
    return y_true, y_pred


def one_vs_rest_mcc(matrix):
    """MCC of the same matrix read as a 2x2 problem (class 0 vs the rest)."""
    matrix = np.asarray(matrix, dtype=np.float64)
    tp = float(matrix[0, 0])
    fn = float(matrix[0, 1:].sum())
    fp = float(matrix[1:, 0].sum())
    tn = float(matrix[1:, 1:].sum())
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return 0.0 if denominator == 0 else (tp * tn - fp * fn) / denominator


def test_multiclass_mcc_matches_sklearn_on_a_known_matrix():
    y_true, y_pred = labels(ARM_A)
    expected = matthews_corrcoef(y_true, y_pred)
    assert multiclass_mcc(ARM_A) == pytest.approx(expected, abs=1e-12)


def test_multiclass_mcc_does_not_truncate_fractional_matrices():
    # A mean matrix over repetitions has fractional cells. Casting to int would
    # silently turn this into a perfect predictor; scaling by an integer must
    # leave the coefficient unchanged.
    fractional = np.array([[1.5, 0.5], [0.5, 2.5]])
    assert multiclass_mcc(fractional) == pytest.approx(multiclass_mcc(fractional * 2), abs=1e-12)
    assert multiclass_mcc(fractional) != pytest.approx(multiclass_mcc(np.floor(fractional)), abs=1e-6)


def test_multiclass_mcc_is_not_a_binary_reduction():
    # If someone replaced the multiclass formula with a one-vs-rest one, the
    # number would differ on this very matrix. That is why the name is explicit.
    assert one_vs_rest_mcc(ARM_A) != pytest.approx(multiclass_mcc(ARM_A), abs=1e-6)


def test_degenerate_two_column_matrix_reports_zero_without_breaking():
    """Arm C's stored matrix: predictions concentrate on two of five classes.

    The MCC is ~0 because the predictions carry (almost) no association with
    the five true classes, not because the formula divides by zero: the pooled
    matrix has mass in two columns and the denominator is positive.
    """
    matrix = np.array([
        [720117, 0, 0, 0, 80013],
        [207630, 0, 0, 0, 23070],
        [31221, 0, 0, 0, 3469],
        [35415, 0, 0, 0, 3935],
        [259092, 0, 0, 0, 28788],
    ])
    value = multiclass_mcc(matrix)
    assert abs(value) < 1e-3
    y_true, y_pred = labels(matrix)
    assert multiclass_mcc(matrix) == pytest.approx(matthews_corrcoef(y_true, y_pred), abs=1e-12)
    predicted = matrix.sum(axis=0)
    assert (predicted > 0).sum() == 2  # two columns, so the denominator is not zero


def _client(client, matrix, samples=None):
    matrix = np.asarray(matrix)
    support = matrix.sum(axis=1)
    recall = np.divide(np.diag(matrix), support, out=np.zeros(5), where=support > 0)
    total = int(matrix.sum())
    return {
        "client": client,
        "round": 7,
        "aggregation_server": 0,
        "device": "cpu",
        "evaluation": {
            "accuracy": float(np.trace(matrix) / total),
            "macro_f1": float(recall.mean()),
            "recall": recall.tolist(),
            "loss": 0.5,
            "samples": samples if samples is not None else total,
            "confusion_matrix": matrix.tolist(),
        },
    }


def test_aggregate_personalized_keeps_every_client_matrix():
    first = np.eye(5, dtype=int) * 10
    second = np.eye(5, dtype=int) * 4
    second[0, 1] = 6  # client 1 misclassifies six benign flows as dos
    third = np.eye(5, dtype=int) * 2

    # Replies arrive in arbitrary order; the artifact must not depend on it.
    pooled = aggregate_personalized(
        [_client(2, third), _client(0, first), _client(1, second)], CLASSES
    )

    assert pooled["personalized_models"] == 3
    assert "per_client" in pooled
    assert [entry["client"] for entry in pooled["per_client"]] == [0, 1, 2]
    assert [entry["confusion_matrix"] for entry in pooled["per_client"]] == [
        first.tolist(), second.tolist(), third.tolist(),
    ]
    assert pooled["confusion_matrix"] == (first + second + third).tolist()
    assert pooled["samples"] == 50 + 26 + 10
    # the harmful client is visible where it matters: its benign recall drops
    assert pooled["per_client"][1]["recall"][0] == pytest.approx(0.4)
    assert pooled["client_macro_f1_min"] == pytest.approx(
        min(pooled["per_client"][i]["macro_f1"] for i in range(3))
    )
    y_true, y_pred = labels(first + second + third)
    assert pooled["mcc"] == pytest.approx(matthews_corrcoef(y_true, y_pred), abs=1e-12)
