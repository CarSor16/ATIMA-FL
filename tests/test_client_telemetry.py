"""Shape and honesty of the per-client telemetry artifact.

The point of the artifact is that every logical client appears in every round,
including the compromised one, and that a missing measurement is reported as
``null`` instead of a plausible-looking zero.
"""

import json

from atima_fl.engine import telemetry


def _metadata(client, *, malicious=False, attack="none", applied=False, **extra):
    metadata = {
        "client": client,
        "round": 1,
        "is_malicious": malicious,
        "attack": attack if applied else "none",
        "attack_applied": applied,
        "original_samples": 1000 + client,
        "trained_samples": 1000 + client,
        "poisoned_labels": 0,
        "local_training_data_altered": False,
        "local_loss": 0.5 + client / 100,
        "local_accuracy": 0.9 - client / 100,
        "local_macro_f1": 0.8,
        "local_metrics_split": "client's own training shard, inference only",
    }
    metadata.update(extra)
    return metadata


def test_ten_rows_one_per_client_including_the_compromised_one(tmp_path):
    rows = []
    for client in range(10):
        if client == 5:
            metadata = _metadata(
                client,
                malicious=True,
                attack="local_class_gradient",
                applied=True,
                gradient_l2=12.5,
                local_delta_l2=3.25,
                added_perturbation_l2_budget=1.625,
                target_class=1,
                target_support=900,
                knowledge="local_shard_only",
            )
            rows.append(telemetry.client_row(client, metadata, 1005, 4.75, True))
        else:
            rows.append(telemetry.client_row(client, _metadata(client), 1000 + client, 3.5, True))

    telemetry.write(tmp_path, [telemetry.round_entry(1, rows)], clients=10)
    stored = json.loads((tmp_path / "client_telemetry.json").read_text())

    assert stored["schema"] == "atima_fl.client_telemetry/1"
    assert stored["clients"] == 10
    assert [row["client"] for row in stored["rounds"][0]["clients"]] == list(range(10))
    assert all(row["participated"] for row in stored["rounds"][0]["clients"])

    malicious = stored["rounds"][0]["clients"][5]
    assert malicious["is_malicious"] is True
    assert malicious["attack"] == "local_class_gradient"
    assert malicious["update_l2"] == 4.75
    assert malicious["attack_telemetry"]["gradient_l2"] == 12.5
    assert malicious["attack_telemetry"]["local_delta_l2"] == 3.25
    assert malicious["attack_telemetry"]["target_class"] == 1

    honest = stored["rounds"][0]["clients"][6]
    assert honest["is_malicious"] is False
    assert honest["attack_telemetry"] == {}
    assert honest["update_l2"] == 3.5


def test_missing_measurements_are_null_not_zero():
    row = telemetry.client_row(3, {"original_samples": 10}, 10, float("nan"), True)
    assert row["local_loss"] is None
    assert row["local_accuracy"] is None
    assert row["update_l2"] is None
    assert row["samples_claimed"] == 10


def test_written_series_replaces_the_previous_one(tmp_path):
    single = telemetry.round_entry(1, [telemetry.client_row(0, _metadata(0), 1000, 1.0, True)])
    telemetry.write(tmp_path, [single], clients=1)
    both = [
        telemetry.round_entry(1, [telemetry.client_row(0, _metadata(0), 1000, 1.0, True)]),
        telemetry.round_entry(2, [telemetry.client_row(0, _metadata(0), 1000, 2.0, True)]),
    ]
    telemetry.write(tmp_path, both, clients=1)
    stored = json.loads((tmp_path / "client_telemetry.json").read_text())
    assert [entry["round"] for entry in stored["rounds"]] == [1, 2]
    assert stored["rounds"][1]["clients"][0]["update_l2"] == 2.0
