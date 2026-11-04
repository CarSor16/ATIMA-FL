"""Regression tests for descriptive, read-only experiment grouping."""

from atima_fl.ui.result_groups import result_group


def manifest(attack="alie", partition="iid", alpha=None):
    return {
        "config": {
            "attack": attack,
            "partition": partition,
            "partition_params": {} if alpha is None else {"alpha": alpha},
            "model": "lopez_cnn",
            "dataset": "edge_iiot",
            "dataset_params": {"task": "prepared_5"},
            "seed": 0,
        }
    }


def test_uses_registered_scientific_attack_taxonomy():
    case = result_group(manifest("min_max"), "campaign_2026-10-21__min_max")
    assert case["category"] == "byzantine_aggregation_disruption"
    assert case["family"] == "Byzantine / aggregation disruption"
    assert case["attack"] == "min_max"
    assert case["campaign_date"] == "2026-10-21"
    assert case["date_source"] == "directory_name"
    assert case["distribution"] == "IID"
    assert case["seed"] == 0


def test_dirichlet_alphas_are_not_merged():
    a = result_group(manifest(partition="dirichlet", alpha=0.1), "experiment")
    b = result_group(manifest(partition="dirichlet", alpha=0.5), "experiment")
    assert a["distribution"] == b["distribution"] == "Non-IID"
    assert a["partition_detail"] == "Dirichlet alpha=0.1"
    assert b["partition_detail"] == "Dirichlet alpha=0.5"
    assert a["campaign_date"] is None
    assert a["date_source"] == "unknown"


def test_unknown_and_invalid_metadata_are_not_fabricated():
    case = result_group(
        {"config": {"attack": "future_attack", "partition": "unregistered"}},
        "unknown_2026-99-99",
    )
    assert case["category"] == "uncategorized"
    assert case["distribution"] == "Unknown"
    assert case["campaign_date"] is None
    assert case["task"] == "Unknown"


def test_clean_run_is_not_reported_as_an_attack():
    case = result_group(manifest("none"), "Baseline_2026-10-11_IID")
    assert case["family"] == "Clean baseline"
    assert case["category"] == "clean_baseline"


def test_task_falls_back_to_dataset_audit():
    case = result_group(
        {"config": {"attack": "label_flip", "partition": "iid"},
         "dataset_audit": {"task": "binary"}},
        "run",
    )
    assert case["task"] == "binary"
    assert case["family"] == "Data poisoning"
