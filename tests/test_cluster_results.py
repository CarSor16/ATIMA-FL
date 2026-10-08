"""Isolated tests: never open a real SSH connection or touch real cluster data."""

import json
import subprocess
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from threading import Thread

import pytest

from atima_fl.ui.app import create_server
from atima_fl.ui.cluster_results import connection_settings, sync_cluster_results


def config(tmp_path, host="cluster.example.edu", user="researcher"):
    payload = {
        "ssh_host": host,
        "ssh_user": user,
        "remote_results_root": "/nas/research/ATIMA-FL/results",
    }
    (tmp_path / "cluster_connection.json").write_text(json.dumps(payload))
    return payload


def test_ssh_import_uses_strict_noninteractive_read_only_command(tmp_path):
    values = config(tmp_path)
    seen = []

    def fake_runner(args, **kwargs):
        seen.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{
                "id": "Binary_Clean",
                "manifest": {"status": "complete", "last_valid_round": 20},
                "final_metrics": {"test": {"accuracy": 0.93}},
            }]),
        )

    response = sync_cluster_results(tmp_path, runner=fake_runner)
    assert response["imported"] == 1
    cmd, kwargs = seen[0]
    assert cmd[0] == "ssh"
    assert "BatchMode=yes" in cmd
    assert "StrictHostKeyChecking=yes" in cmd
    assert cmd[-3:] == [values["ssh_user"] + "@" + values["ssh_host"], "python3", "-"]
    assert kwargs["input"].find(values["remote_results_root"]) >= 0
    assert kwargs["timeout"] <= 35
    assert json.loads((tmp_path / "results/Binary_Clean/manifest.json").read_text())["status"] == "complete"
    assert json.loads((tmp_path / "results/Binary_Clean/final_metrics.json").read_text())["test"]["accuracy"] == 0.93
    assert not (tmp_path / "results/Binary_Clean/trajectory.h5").exists()


@pytest.mark.parametrize("change", [
    {"ssh_host": "-oProxyCommand=bad"},
    {"ssh_host": "host; touch /tmp/malicious"},
    {"ssh_user": "-invalid"},
    {"remote_results_root": "../../bad"},
    {"remote_results_root": "/nas/../secrets"},
])
def test_config_rejects_unsafe_connection_values(tmp_path, change):
    config(tmp_path)
    path = tmp_path / "cluster_connection.json"
    values = json.loads(path.read_text())
    values.update(change)
    path.write_text(json.dumps(values))
    with pytest.raises(ValueError):
        connection_settings(tmp_path)


@pytest.mark.parametrize("name", ["../escape", ".hidden/escape", "-invalid", ".", ".."])
def test_ssh_import_rejects_untrusted_experiment_names(tmp_path, name):
    config(tmp_path)
    def runner(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"id": name, "manifest": {"status": "complete"}, "final_metrics": {}}])
        )
    with pytest.raises(ValueError):
        sync_cluster_results(tmp_path, runner=runner)
    assert not (tmp_path / "results").exists()


def test_ssh_connection_failures_are_generic_and_leave_workspace_unchanged(tmp_path):
    config(tmp_path)
    def fail(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 255, "", "sensitive ssh detail")
    with pytest.raises(ValueError, match="Cluster SSH read failed") as exc:
        sync_cluster_results(tmp_path, runner=fail)
    assert "sensitive ssh detail" not in str(exc.value)
    assert not (tmp_path / "results").exists()


def test_web_status_endpoint_and_token_required_for_sync(tmp_path, monkeypatch):
    config(tmp_path)
    server = create_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        status = json.load(urlopen(url + "/api/cluster-status"))
        assert status == {
            "configured": True, "host": "cluster.example.edu",
            "workspace": str(tmp_path.resolve()),
            "config_path": str(tmp_path.resolve() / "cluster_connection.json"),
        }
        with pytest.raises(HTTPError) as caught:
            urlopen(Request(
                url + "/api/sync-cluster-results", data=b"{}",
                headers={"Content-Type": "application/json"}
            ))
        assert caught.value.code == 403
        monkeypatch.setattr(
            "atima_fl.ui.app.sync_cluster_results",
            lambda workspace: {"imported": 2, "source": "test"}
        )
        token = json.load(urlopen(url + "/api/catalog"))["token"]
        synced = json.load(urlopen(Request(
            url + "/api/sync-cluster-results", data=b"{}",
            headers={"Content-Type": "application/json", "X-ATIMA-Token": token}
        )))
        assert synced["imported"] == 2
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_stored_password_path_is_selected_without_shell_or_password_logs(tmp_path, monkeypatch):
    config(tmp_path)
    invoked = []
    monkeypatch.setattr(
        "atima_fl.ui.cluster_results.password_ssh",
        lambda settings, script: invoked.append((settings, script)) or json.dumps([
            {"id": "Clean", "manifest": {"status": "complete"}, "final_metrics": {}}
        ]),
    )
    outcome = sync_cluster_results(tmp_path)
    assert outcome["imported"] == 1
    assert len(invoked) == 1
    assert "import json" in invoked[0][1]
    assert "validation_history.json" in invoked[0][1]


def test_password_ssh_returns_none_without_stored_credential(monkeypatch):
    from atima_fl.ui.cluster_results import password_ssh
    monkeypatch.setattr(
        "atima_fl.ui.cluster_credentials.get_password", lambda user, host: None
    )
    assert password_ssh(
        {"ssh_host": "cluster.example.edu", "ssh_user": "researcher"}, "print('ok')"
    ) is None



def test_import_round_histories_and_make_verified_model_pairs(tmp_path):
    from atima_fl.ui.app import results

    config(tmp_path)
    identity = {"engine": "same-source"}
    runtime = {"python": "3.12", "device": "cpu"}
    classes = ["benign", "dos"]
    runs = []
    for name, attack, model, pair, legacy in [
        ("Baseline", "none", "mlp", "pair-1", False),
        ("LabelFlip", "label_flip", "mlp", "pair-1", False),
        ("Baseline_CNN", "none", "lopez_cnn", "pair-2", True),
        ("Wrong_source", "alie", "mlp", "pair-1", True),
    ]:
        manifest = {
            "status": "complete", "last_valid_round": 2, "pair_id": pair,
            "source_identity": identity if name != "Wrong_source" else {"engine": "different"},
            "runtime": runtime,
            "config": {"attack": attack, "model": model},
            "dataset_audit": {"classes": classes},
        }
        record = {
            "id": name, "manifest": manifest,
            "final_metrics": {"test": {
                "accuracy": 0.8, "macro_f1": 0.7,
                "per_class": {"benign": {"recall": 0.9}, "dos": {"recall": 0.6}},
                "confusion_matrix": [[9, 1], [4, 6]]
            }},
        }
        if not legacy:
            record["validation_history"] = [
                {"round": 1, "accuracy": 0.5, "macro_f1": 0.4, "recall": [0.9, 0.3],
                 "metadata": {"secret": "must not be imported"}},
                {"round": 2, "accuracy": 0.8, "macro_f1": 0.7, "recall": [0.9, 0.6]},
            ]
        runs.append(record)

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(runs))

    imported = sync_cluster_results(tmp_path, runner=runner)
    assert imported["imported"] == 4
    assert "validation_history.json" in imported["files"]
    file = tmp_path / "results/LabelFlip/validation_history.json"
    data = json.loads(file.read_text())
    assert [row["round"] for row in data] == [1, 2]
    assert "metadata" not in file.read_text()
    assert not (tmp_path / "results/LabelFlip/trajectory.h5").exists()
    current = {row["id"]: row for row in results(tmp_path)}
    assert current["LabelFlip"]["baseline_id"] == "Baseline"
    assert current["Wrong_source"]["baseline_id"] is None
    assert len(current["LabelFlip"]["history"]) == 2
    assert current["Baseline_CNN"]["history"] == []


@pytest.mark.parametrize("history", [
    [{"round": 2, "macro_f1": 0.5}, {"round": 1, "macro_f1": 0.4}],
    [{"round": 1, "macro_f1": 2.0}],
    [{"round": 1, "recall": [0.5, -0.1]}],
    [{"round": 1, "macro_f1": float("nan")}],
    {"round": 1},
    [{"round": True}],
])
def test_invalid_history_rejected_without_partial_result_import(tmp_path, history):
    config(tmp_path)

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([{
            "id": "Clean", "manifest": {"status": "complete", "last_valid_round": 2},
            "final_metrics": {}, "validation_history": history,
        }]))

    with pytest.raises(ValueError):
        sync_cluster_results(tmp_path, runner=runner)
    assert not (tmp_path / "results").exists()


def test_reimport_removes_stale_validation_history(tmp_path):
    config(tmp_path)
    records = []

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([{
            "id": "Reused", "manifest": {"status": "complete", "last_valid_round": 1},
            "final_metrics": {},
            **({"validation_history": [{"round": 1, "macro_f1": 0.7}]} if not records else {}),
        }]))

    sync_cluster_results(tmp_path, runner=runner)
    file = tmp_path / "results/Reused/validation_history.json"
    assert file.is_file()
    records.append(1)
    sync_cluster_results(tmp_path, runner=runner)
    assert not file.exists()


def test_results_api_returns_compact_histories_and_verified_pair_id(tmp_path):
    from atima_fl.ui.app import results
    root = tmp_path / "results"
    for name, attack, source in [("Clean", "none", "v1"), ("Attack", "alie", "v1"),
                                 ("Unmatched", "alie", "v2")]:
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({
            "status": "complete", "pair_id": "paired", "last_valid_round": 1,
            "source_identity": {"version": source}, "runtime": {"device": "cpu"},
            "config": {"attack": attack, "model": "mlp"},
        }))
        (folder / "validation_history.json").write_text(json.dumps([
            {"round": 1, "macro_f1": 0.6, "accuracy": 0.7,
             "per_class": {"benign": {"recall": 0.2}}, "recall": [0.8, 0.4]}
        ]))
    values = {v["id"]: v for v in results(tmp_path)}
    assert values["Attack"]["baseline_id"] == "Clean"
    assert values["Unmatched"]["baseline_id"] is None
    assert values["Clean"]["history"] == [{"round": 1, "accuracy": 0.7,
                                              "macro_f1": 0.6, "recall": [0.8, 0.4]}]


def test_absent_source_identity_does_not_falsely_match_clean_run(tmp_path):
    from atima_fl.ui.app import results
    for name, attack in [("Clean", "none"), ("Attack", "alie")]:
        folder = tmp_path / "results" / name
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({
            "status": "complete", "pair_id": "same", "last_valid_round": 3,
            "config": {"attack": attack},
        }))
    runs = {row["id"]: row for row in results(tmp_path)}
    assert runs["Attack"]["baseline_id"] is None



def test_missing_connection_error_shows_actual_active_workspace(tmp_path):
    with pytest.raises(ValueError, match="cluster_connection.json not found") as exc:
        sync_cluster_results(tmp_path, runner=lambda *args, **kwargs: None)
    assert str(tmp_path.resolve()) in str(exc.value)


def test_cluster_status_exposes_missing_config_location_not_secrets(tmp_path):
    server = create_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        status = json.load(urlopen(url + "/api/cluster-status"))
        assert status == {
            "configured": False, "host": None,
            "workspace": str(tmp_path.resolve()),
            "config_path": str(tmp_path.resolve() / "cluster_connection.json"),
        }
    finally:
        server.shutdown()
        thread.join()
        server.server_close()



def test_results_api_exposes_task_and_audited_split_hashes_for_manual_comparison(tmp_path):
    from atima_fl.ui.app import results
    folder = tmp_path / "results" / "Binary_Clean"
    folder.mkdir(parents=True)
    hashes = {
        "train": "sha-train", "validation": "sha-valid",
        "test": "sha-test", "feature_schema.json": "sha-schema",
        "label_mapping.json": "sha-map", "preprocessor.json": "sha-prep",
        "client_0": "do-not-need-to-expose-client-shard",
    }
    (folder / "manifest.json").write_text(json.dumps({
        "status": "complete", "last_valid_round": 10,
        "config": {
            "attack": "none", "dataset": "edge_iiot",
            "dataset_params": {"task": "binary"},
        },
        "dataset_audit": {
            "task": "binary", "classes": ["Normal", "Attack"],
            "hashes": hashes, "client_counts": {"0": 100},
        },
    }))
    (folder / "final_metrics.json").write_text(json.dumps({
        "test": {"samples": 200,
                 "per_class": {"Normal": {"support": 100}, "Attack": {"support": 100}}}
    }))
    result = results(tmp_path)[0]
    assert result["dataset_identity"]["task"] == "binary"
    assert result["dataset_identity"]["hashes"]["test"] == "sha-test"
    assert result["dataset_identity"]["hashes"]["feature_schema.json"] == "sha-schema"
    assert "client_0" not in result["dataset_identity"]["hashes"]
    assert "client_counts" not in result["dataset_identity"]


def test_results_api_old_manifest_missing_audit_is_not_misrepresented(tmp_path):
    from atima_fl.ui.app import results
    folder = tmp_path / "results" / "Old"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "status": "complete", "config": {"dataset": "edge_iiot", "attack": "none"},
    }))
    result = results(tmp_path)[0]
    assert result["dataset_identity"]["task"] is None
    assert all(value is None for value in result["dataset_identity"]["hashes"].values())
