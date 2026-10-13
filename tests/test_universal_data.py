"""Synthetic cross-format dataset tests; no university data or cluster required."""
import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.universal_data import inspect, prepare, prepared_summary


@pytest.fixture
def raw(tmp_path):
    source = tmp_path / "flows.csv"
    pd.DataFrame({
        "session_id": list(range(120)),
        "src_ip": [f"10.0.0.{i % 20}" for i in range(120)],
        "duration": [float(i) + 1.0 for i in range(120)],
        "bytes": [float(i * i + 1) for i in range(120)],
        "protocol": [["tcp", "udp", "icmp"][i % 3] for i in range(120)],
        "Attack": [["Benign", "DDoS", "Scan"][i % 3] for i in range(120)],
        "Label": [0 if i % 3 == 0 else 1 for i in range(120)],
    }).to_csv(source, index=False)
    return source


def test_inspect_prepare_and_both_tasks(tmp_path, raw):
    found = inspect(raw)
    assert found["format"] == "tabular"
    assert {"Attack", "Label"} <= {
        entry["column"] for entry in found["label_candidates"]
    }
    output = tmp_path / "prepared"
    info = prepare(raw, output, "Attack", benign_label="Benign", clients=10, seed=42,
                   exclude_columns=["session_id"])
    assert info["num_classes"] == 3 and info["input_dim"] == 5
    assert set(info["task_options"]) == {"binary", "multiclass"}
    assert prepared_summary(output) == info

    base = ExperimentConfig(
        dataset="universal_tabular", dataset_root=str(output),
        dataset_params={"task": "multiclass"}, num_classes=3,
        input_dim=5, clients=10, seed=42,
    ).validate()
    from atima_fl.engine.data import open_dataset
    reader = open_dataset(base)
    audit = reader.audit()
    assert len(audit["client_counts"]) == 10
    assert len(reader.split("test").x) > 0
    assert sum(audit["rows"].values()) == 120
    binary = replace(base, dataset_params={"task": "binary"}, num_classes=2).validate()
    second = open_dataset(binary)
    second.audit()
    assert set(second.split("test").y) == {0, 1}

    mapping = json.loads((output / "label_mapping.json").read_text())
    assert set(mapping) == {"Benign", "DDoS", "Scan"}
    schema = json.loads((output / "feature_schema.json").read_text())
    assert "Attack" not in schema["source_features"]
    assert "Label" not in schema["source_features"]
    assert "src_ip" not in schema["source_features"]
    assert "session_id" not in schema["source_features"]
    with pytest.raises(FileExistsError):
        prepare(raw, output, "Attack", benign_label="Benign")


def test_reject_mismatched_task_and_tampered_shard(tmp_path, raw):
    output = tmp_path / "prepped"
    info = prepare(raw, output, "Attack", clients=10, seed=2)
    cfg = ExperimentConfig(
        dataset="universal_tabular", dataset_root=str(output),
        dataset_params={"task": "multiclass"}, num_classes=3, input_dim=info["input_dim"],
    ).validate()
    from atima_fl.engine.data import open_dataset

    reader = open_dataset(cfg)
    assert reader.audit()["task"] == "multiclass"
    with pytest.raises(ValueError, match="benign"):
        open_dataset(replace(cfg, num_classes=2,
                             dataset_params={"task": "binary"}).validate())
    shard = output / "iid" / "clients" / "client_00.parquet"
    frame = pd.read_parquet(shard)
    col = reader.features[0]
    frame.loc[0, col] += np.float32(1)
    frame.to_parquet(shard, index=False)
    with pytest.raises(ValueError, match="fingerprints"):
        reader.audit()


def test_no_label_inference_from_heuristics_or_empty_benign(tmp_path, raw):
    found = inspect(raw)
    assert found["requires_confirmation"] is True
    with pytest.raises(ValueError, match="Declared benign"):
        prepare(raw, tmp_path / "bad", "Attack", benign_label="made-up")
    with pytest.raises(ValueError, match="label_column"):
        prepare(raw, tmp_path / "bad", "")
    with pytest.raises(ValueError, match="exceeds"):
        prepare(raw, tmp_path / "bad", "Attack", max_rows=30)


def test_local_launch_uses_cpu_without_slurm(monkeypatch):
    from types import SimpleNamespace
    from atima_fl.adapters.flower.launch import launch

    recorded = {}
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr("atima_fl.engine.data.open_dataset",
                        lambda c: SimpleNamespace(audit=lambda: {"test": "synthetic"}))
    monkeypatch.setattr("flwr.simulation.run_simulation",
                        lambda **kwargs: recorded.update(kwargs))
    c = replace(ExperimentConfig(), compute_device="cpu", client_cpus=1)
    launch(c, preflight_only=True, local=True)
    launch(c, local=True)
    assert recorded["backend_config"]["init_args"]["num_gpus"] == 0
    assert recorded["backend_config"]["client_resources"]["num_gpus"] == 0



def test_local_dataset_manager_api_without_cluster(tmp_path, raw):
    from threading import Thread
    from urllib.request import Request, urlopen

    from atima_fl.ui.app import create_server

    server = create_server(tmp_path / "workspace", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        catalog = json.load(urlopen(url + "/api/catalog"))
        headers = {
            "Content-Type": "application/json",
            "X-ATIMA-Token": catalog["token"],
        }

        def post(endpoint, payload):
            request = Request(
                url + endpoint, data=json.dumps(payload).encode(), headers=headers
            )
            return json.load(urlopen(request))

        data = post("/api/datasets/inspect", {"path": str(raw)})
        assert any(v["column"] == "Attack" for v in data["label_candidates"])
        prepared = post("/api/datasets/prepare", {
            "path": str(raw), "output": str(tmp_path / "via-ui"),
            "label_column": "Attack", "benign_label": "Benign",
            "clients": 10, "seed": 7, "exclude_columns": [],
        })
        assert prepared["num_classes"] == 3
        looked_up = post("/api/datasets/prepared", {"path": prepared["path"]})
        assert looked_up["input_dim"] == prepared["input_dim"]
        html = urlopen(url + "/").read().decode()
        assert 'id="dataset-manager"' in html
        assert 'id="ud-source-path"' in html
        assert 'id="ud-prepare"' in html
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
