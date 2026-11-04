"""Regression coverage for descriptive campaign grouping."""

from atima_fl.ui.result_groups import classify_run


def _manifest(attack="alie", partition="iid", task="prepared_5"):
    return {
        "config": {
            "attack": attack,
            "partition": partition,
            "dataset": "edge_iiot",
            "dataset_params": {"task": task},
            "model": "lopez_cnn",
            "seed": 2026,
        }
    }


def test_iid_historical_campaign():
    result = classify_run(
        _manifest(), "campaign_2026-10-11_sixrun_v2__ALIE_CNN_Macro5"
    )
    assert result["family"] == "Model poisoning"
    assert result["attack"] == "alie"
    assert result["date"] == "2026-10-11"
    assert result["distribution"] == "IID"
    assert result["task"] == "prepared_5"
    assert result["seed"] == 2026


def test_non_iid_dirichlet_and_attack_taxonomy():
    result = classify_run(
        _manifest("update_scaling", "dirichlet", "original_16"),
        "campaign_2026-10-28_realistic_byzantine__UpdateScaling",
    )
    assert result["distribution"] == "Non-IID"
    assert result["partition"] == "dirichlet"
    assert result["family"] == "Model poisoning"
    assert result["task"] == "original_16"


def test_no_invented_date_or_distribution():
    result = classify_run(
        {"config": {"attack": "none", "partition": "custom_partition"}},
        "older_baseline",
    )
    assert result["date"] == "Unknown"
    assert result["distribution"] == "Unknown"
    assert result["family"] == "Clean baseline"


def test_unknown_attack_remains_visible():
    result = classify_run(_manifest("future_attack"), "2026-10-30_new")
    assert result["attack"] == "future_attack"
    assert result["family"] == "Other / unclassified"
