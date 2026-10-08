import numpy as np
from atima_fl.core.contracts import Component


def evaluate(y, p, classes, params):
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        matthews_corrcoef,
    )

    n_classes = len(classes)
    if (
        p.shape != (len(y), n_classes)
        or not np.isfinite(p).all()
        or (p < 0).any()
        or not np.allclose(p.sum(axis=1), 1, atol=1e-5)
    ):
        raise ValueError("Invalid predictions cannot be converted into accuracy/F1")
    predicted = np.argmax(p, axis=1)
    labels = range(n_classes)
    report = classification_report(
        y, predicted, labels=labels, target_names=classes, output_dict=True, zero_division=0
    )
    recalls = [report[name]["recall"] for name in classes]
    epsilon = params["probability_clip"]
    return {
        "accuracy": float(accuracy_score(y, predicted)),
        "macro_f1": float(f1_score(y, predicted, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(y, predicted, labels=labels, average="weighted", zero_division=0)
        ),
        "balanced_accuracy": float(np.mean(recalls)),
        "mcc": float(matthews_corrcoef(y, predicted)),
        "loss": float(-np.log(np.maximum(p[np.arange(len(y)), y], epsilon)).mean()),
        "recall": recalls,
        "per_class": {name: report[name] for name in classes},
        "confusion_matrix": confusion_matrix(y, predicted, labels=labels).tolist(),
        "samples": len(y),
        "loss_definition": f"mean negative log true-class probability, clipped at {epsilon}",
    }


PLUGIN = Component(
    "classification",
    "metrics",
    "Multiclass metrics",
    "Macro/weighted F1, recall, precision, balanced accuracy, MCC, loss and confusion matrix.",
    {"probability_clip": {"type": "number", "default": 1e-7, "minimum": 1e-12, "maximum": 0.01}},
    {"evaluate": evaluate},
    translations={
        "it": {
            "title": "Metriche multiclasse",
            "description": "Macro/weighted F1, recall, precision, balanced accuracy, MCC, loss e confusion matrix.",
        }
    },
)
