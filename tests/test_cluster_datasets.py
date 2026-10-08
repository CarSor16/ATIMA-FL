"""Read-only cluster dataset discovery and truthful plugin/task availability."""

import contextlib
import gzip
import io
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from atima_fl.ui.cluster_datasets import (
    _REMOTE_READ, configured_dataset_paths, discover_cluster_datasets,
)
from atima_fl.ui.app import create_server


def configured(tmp_path):
    (tmp_path / "cluster_connection.json").write_text(json.dumps({
        "ssh_host": "cluster.example.edu", "ssh_user": "researcher",
        "remote_results_root": "/safe/results",
    }), encoding="utf-8")
    (tmp_path / "deployment_defaults.json").write_text(json.dumps({
        "dataset_root": "/safe/prepared/edge",
    }), encoding="utf-8")
    (tmp_path / "cluster_dataset_paths.json").write_text(json.dumps({
        "nf_botiot": "/safe/nfv2/NF-BoT-IoT-v2.csv.gz",
    }), encoding="utf-8")


def test_paths_only_use_explicit_configured_sources(tmp_path):
    configured(tmp_path)
    assert configured_dataset_paths(tmp_path) == {
        "edge_iiot": "/safe/prepared/edge",
        "nf_botiot": "/safe/nfv2/NF-BoT-IoT-v2.csv.gz",
    }


@pytest.mark.parametrize("value", [
    "../../etc/passwd", "/safe/../passwd", "/safe/./file",
    "/a\nb", "/path\x00unsafe", "C:\\fake\\path", "/a\tb",
])
def test_reject_unsafe_dataset_paths(tmp_path, value):
    configured(tmp_path)
    (tmp_path / "cluster_dataset_paths.json").write_text(json.dumps({
        "nf_botiot": value
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="dataset path|Cluster dataset path"):
        configured_dataset_paths(tmp_path)


def test_reject_unknown_dataset_path_keys(tmp_path):
    configured(tmp_path)
    (tmp_path / "cluster_dataset_paths.json").write_text(json.dumps({
        "nf_unknown": "/safe/nfv2/raw.csv"
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected dataset identifiers"):
        configured_dataset_paths(tmp_path)


def inventory():
    return {
        "edge_iiot": {
            "path": "/safe/prepared/edge", "found": True,
            "source_labels": ["Normal", "DDoS_TCP"], "source_complete": True,
            "rows_scanned": 123, "note": "",
            "prepared_classes": ["benign", "dos", "infog", "inject", "malware"],
            "observed_by_split": {
                "train": {"Normal": 70, "DDoS_TCP": 30},
                "validation": {"Normal": 5, "DDoS_TCP": 4},
                "test": {"Normal": 10, "DDoS_TCP": 4},
            },
        },
        "nf_botiot": {
            "path": "/safe/nfv2/NF-BoT-IoT-v2.csv.gz",
            "found": True, "source_labels": ["Benign", "DDoS"],
            "source_complete": False, "rows_scanned": 15, "note": "sample only",
            "observed_counts_sample": {"Benign": 10, "DDoS": 5},
        },
    }


def test_verified_edge_availability_and_nf_sample_not_executable(tmp_path):
    configured(tmp_path)
    invocations = []

    def runner(command, **kwargs):
        invocations.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(inventory()))

    result = discover_cluster_datasets(tmp_path, runner=runner)
    edge = result["datasets"]["edge_iiot"]
    assert edge["training_supported"]
    assert edge["task_availability"]["binary"]["available"]
    assert not edge["task_availability"]["family_6"]["available"]
    assert not edge["task_availability"]["fine_15"]["available"]
    assert edge["task_availability"]["prepared_5"]["available"]
    assert result["datasets"]["nf_botiot"]["source_labels"] == ["Benign", "DDoS"]
    assert result["datasets"]["nf_botiot"]["training_supported"] is False
    assert "nf_unsw_nb15" in result["unconfigured"]
    command, kwargs = invocations[0]
    assert command[0] == "ssh"
    assert "StrictHostKeyChecking=yes" in command
    assert "BatchMode=yes" in command
    assert "/safe/prepared/edge" in kwargs["input"]
    assert "pd.read_parquet" in kwargs["input"]
    assert "Path(value)" in kwargs["input"]
    assert kwargs["timeout"] <= 60
    assert result["note"].startswith("Read-only")


def test_reject_malformed_cluster_data_without_mutating_workspace(tmp_path):
    configured(tmp_path)
    data = inventory()
    data["nf_botiot"]["rows_scanned"] = "fifteen"

    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(data))

    with pytest.raises(ValueError, match="record count"):
        discover_cluster_datasets(tmp_path, runner=runner)
    assert not (tmp_path / "results").exists()


def test_reject_unexpected_dataset_in_cluster_response(tmp_path):
    configured(tmp_path)
    data = inventory()
    data["foreign"] = data.pop("nf_botiot")

    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(data))

    with pytest.raises(ValueError, match="Unexpected cluster dataset inventory"):
        discover_cluster_datasets(tmp_path, runner=runner)


def test_remote_script_reads_only_explicit_nf_csv_and_samples(tmp_path):
    raw = tmp_path / "nf.csv.gz"
    with gzip.open(raw, "wt", encoding="utf-8", newline="") as handle:
        handle.write("Attack,Label,extra\nBenign,0,first\nDoS,1,second\n")
    paths = {"nf_botiot": str(raw)}
    script = _REMOTE_READ.replace("PATHS_LITERAL", repr(json.dumps(paths)))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(script, "<read-only-inventory>", "exec"), {})
    data = json.loads(output.getvalue())
    record = data["nf_botiot"]
    assert record["found"]
    assert not record["source_complete"]
    assert record["rows_scanned"] == 2
    assert record["source_labels"] == ["Benign", "DoS"]
    assert record["observed_counts_sample"] == {"Benign": 1, "DoS": 1}
    assert raw.is_file()


def test_gui_cluster_discovery_requires_session_token_and_has_no_client_paths(
    tmp_path, monkeypatch
):
    configured(tmp_path)
    import atima_fl.ui.app as app

    def fake_read(workspace):
        return {
            "datasets": {"edge_iiot": {"training_supported": False}},
            "unconfigured": [], "note": "fixture",
        }

    monkeypatch.setattr(app, "discover_cluster_datasets", fake_read)
    server = create_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        token = json.load(urlopen(url + "/api/catalog"))["token"]
        with pytest.raises(HTTPError) as denial:
            urlopen(Request(url + "/api/discover-cluster-datasets",
                            b"{}", headers={"Content-Type": "application/json"}))
        assert denial.value.code == 403
        headers = {"Content-Type": "application/json", "X-ATIMA-Token": token}
        data = json.load(urlopen(Request(url + "/api/discover-cluster-datasets",
                                         b"{}", headers=headers)))
        assert data["datasets"]["edge_iiot"]["training_supported"] is False
        with pytest.raises(HTTPError) as denial:
            urlopen(Request(url + "/api/discover-cluster-datasets",
                            b'{"remote_path":"/etc"}', headers=headers))
        assert denial.value.code == 422
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_ui_does_not_offer_unimplemented_nf_plugins_as_executable():
    # Source inspection as an additive UI regression check; no browser dependency.
    static = Path(__file__).resolve().parents[1] / "src/atima_fl/ui/static"
    script = (static / "app.js").read_text(encoding="utf-8")
    html = (static / "index.html").read_text(encoding="utf-8")
    assert 'option.disabled=true;' in script
    assert 'NF-CSE-CIC-IDS2018-v2' in script
    assert 'NF-UNSW-NB15-v2' in script
    assert 'NF-BoT-IoT-v2' in script
    assert 'NF-ToN-IoT-v2' in script
    assert 'Edge-IIoT · 2 classes · Binary' in script
    assert 'Edge-IIoT · 6 classes · Attack families' in script
    assert 'Edge-IIoT · 15 classes · Detailed attacks' in script
    assert 'id="discover-cluster-datasets"' in html
    assert 'id="cluster-dataset-inventory"' in html
    assert "(source labels required for 2/6/15)" not in script
