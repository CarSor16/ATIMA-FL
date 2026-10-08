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
    runner = lambda *a, **k: SimpleNamespace(
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
        assert status == {"configured": True, "host": "cluster.example.edu"}
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
