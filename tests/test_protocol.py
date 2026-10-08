from dataclasses import replace
import json
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
import pytest
import torch
from flwr.app import ArrayRecord, ConfigRecord, Context, Message, MetricRecord, RecordDict
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.componenti.dati.edge_iiot import FEATURES
from atima_fl.engine.data import open_dataset as EdgeData
from atima_fl.engine.client import train_local, submit_local
from atima_fl.adapters.flower.server import _run_protocol, run_experiment


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    rng = np.random.default_rng(7)
    offset = 0
    for split, n in [("train", 100), ("validation", 20), ("test", 20)]:
        frame = pd.DataFrame(rng.uniform(size=(n, 60)).astype(np.float32), columns=FEATURES)
        frame["source_row_id"] = np.arange(offset, offset + n)
        frame["input_fingerprint"] = [f"fingerprint_{i}" for i in range(offset, offset + n)]
        frame["target_id"] = np.arange(n) % 5
        frame["fine_label"] = "fixture"
        frame.to_parquet(root / f"{split}_scaled.parquet", index=False)
        offset += n
        if split == "train":
            folder = root / "iid"
            (folder / "clients").mkdir(parents=True)
            assignment = frame[["source_row_id"]].copy()
            assignment["client_id"] = np.arange(n) // 10
            assignment.to_parquet(folder / "client_assignment.parquet", index=False)
            for cid in range(10):
                frame.iloc[cid * 10 : (cid + 1) * 10].to_parquet(
                    folder / "clients" / f"client_{cid:02d}.parquet", index=False
                )
    for name, content in [
        ("feature_schema.json", {"columns": FEATURES}),
        ("label_mapping.json", {f"class{i}": i for i in range(5)}),
        ("preprocessor.json", {"fixture": True}),
        ("manifest.json", {"fixture": True}),
    ]:
        (root / name).write_text(json.dumps(content))
    return root


class SoftwareGrid:
    """Native Flower Message fixture, serial CPU only; not Ray/GPU validation."""

    def get_node_ids(self):
        return list(range(10))

    def send_and_receive(self, messages, timeout):
        for message in messages:
            cid = message.metadata.dst_node_id
            cmd = message.content["config"]
            c = ExperimentConfig.from_dict(json.loads(cmd["config_json"]))
            values = message.content["arrays"].to_numpy_ndarrays()
            if cmd["phase"] == "train":
                values, meta = train_local(
                    c, Path(cmd["run_dir"]), cid, cmd["server-round"], values, EdgeData(c), "cpu"
                )
            else:
                counts = {int(k): v for k, v in json.loads(cmd["counts_json"]).items()}
                values, meta = submit_local(
                    c, Path(cmd["run_dir"]), cid, cmd["server-round"], values, counts
                )
            yield Message(
                content=RecordDict(
                    {
                        "arrays": ArrayRecord(numpy_ndarrays=values),
                        "metrics": MetricRecord(
                            {"client-id": cid, "num-examples": meta["original_samples"]}
                        ),
                        "audit": ConfigRecord({"metadata_json": json.dumps(meta)}),
                    }
                ),
                reply_to=message,
            )


@pytest.mark.parametrize(
    "attack,knowledge",
    [
        (a, k)
        for a, k in [
            ("label_flip", "local"),
            ("alie", "local"),
            ("ipm", "oracle"),
            ("fang", "oracle"),
            ("model_replacement", "local"),
            ("random_labels", "local"),
            ("feature_noise", "local"),
            ("sign_flip", "local"),
            ("gaussian_noise", "local"),
            ("update_scaling", "local"),
        ]
    ],
)
def test_full_two_phase_protocol_pair_and_hdf(dataset, tmp_path, attack, knowledge, monkeypatch):
    torch.set_num_threads(1)
    c = ExperimentConfig(
        name="clean",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        rounds=2,
        model_params={"hidden": [8, 4]},
        local_epochs=1,
        attack_start=2,
    ).validate()
    clean = _run_protocol(SoftwareGrid(), c, "cpu")
    attacked = replace(
        c,
        name=attack,
        attack=attack,
        attack_params=({"knowledge": knowledge} if attack in ("alie", "ipm", "fang") else {}),
        paired_clean=str(clean),
    )
    run = _run_protocol(SoftwareGrid(), attacked, "cpu")
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["status"] == "complete" and manifest["last_valid_round"] == 2
    with h5py.File(run / "trajectory.h5") as file, h5py.File(clean / "trajectory.h5") as clean_file:
        assert file.attrs["last_valid_round"] == 2
        for key in file["rounds/round_0001/global_after"]:
            assert np.array_equal(
                file[f"rounds/round_0001/global_after/{key}"][...],
                clean_file[f"rounds/round_0001/global_after/{key}"][...],
            )
        assert len(file["rounds/round_0002/clients"]) == 10
        meta = json.loads(file["rounds/round_0002/clients/client_00"].attrs["metadata_json"])
        assert meta["is_malicious"] and meta["active"]
    if attack == "model_replacement":
        assert "attack_metrics" in json.loads((run / "final_metrics.json").read_text())
    if attack == "ipm":
        monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl_cache"))
        from atima_fl.engine.analysis import compare

        output = tmp_path / "plots"
        result = compare(clean, run, output)
        assert len(result["rounds"]) == 2
        assert result["rounds"][0]["weight_l2"] == 0
        assert (output / "paired_trajectory.png").stat().st_size > 1000
        assert (output / "per_class_recall.png").stat().st_size > 1000


def test_audit_detects_split_leakage(dataset, tmp_path):
    c = ExperimentConfig(name="fixture", dataset_root=str(dataset), output_root=str(tmp_path))
    assert EdgeData(c).audit()["rows"]["train"] == 100
    frame = pd.read_parquet(dataset / "validation_scaled.parquet")
    frame.loc[0, "source_row_id"] = 0
    frame.to_parquet(dataset / "validation_scaled.parquet", index=False)
    with pytest.raises(ValueError, match="leakage"):
        EdgeData(c).audit()


def test_production_rejects_cpu(dataset, tmp_path):
    c = ExperimentConfig(name="fixture", dataset_root=str(dataset), output_root=str(tmp_path))
    with pytest.raises(RuntimeError, match="require CUDA"):
        run_experiment(SoftwareGrid(), c, "cpu")


def test_native_client_app_callback_routing(dataset, tmp_path, monkeypatch):
    import atima_fl.adapters.flower.client as module

    original_train = module.train_local
    # Explicit software mock only. Training remains CPU and is recorded as CPU.
    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(
        module,
        "train_local",
        lambda c, r, cid, round_id, g, d, device: original_train(c, r, cid, round_id, g, d, "cpu"),
    )

    class CallbackGrid(SoftwareGrid):
        def send_and_receive(self, messages, timeout):
            for message in messages:
                cid = message.metadata.dst_node_id
                context = Context(
                    run_id=1,
                    node_id=cid,
                    node_config={"partition-id": cid},
                    state=RecordDict(),
                    run_config={},
                )
                yield module.app(message, context)

    c = ExperimentConfig(
        name="callback",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        rounds=1,
        model_params={"hidden": [8, 4]},
        local_epochs=1,
    )
    run = _run_protocol(CallbackGrid(), c, "cpu")
    with h5py.File(run / "trajectory.h5") as file:
        meta = json.loads(file["rounds/round_0001/clients/client_00"].attrs["metadata_json"])
        assert meta["device"] == "cpu"


def test_pre_attack_pair_divergence_is_rejected(dataset, tmp_path):
    torch.set_num_threads(1)
    c = ExperimentConfig(
        name="clean",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        rounds=2,
        model_params={"hidden": [8, 4]},
        local_epochs=1,
        attack_start=2,
    )
    clean = _run_protocol(SoftwareGrid(), c, "cpu")

    class BadGrid(SoftwareGrid):
        def send_and_receive(self, messages, timeout):
            phase = messages[0].content["config"]["phase"]
            for reply in super().send_and_receive(messages, timeout):
                if phase == "submit":
                    values = reply.content["arrays"].to_numpy_ndarrays()
                    reply.content["arrays"] = ArrayRecord(
                        numpy_ndarrays=[v + np.float32(0.01) for v in values]
                    )
                yield reply

    attacked = replace(c, name="bad_pair", attack="label_flip", paired_clean=str(clean))
    with pytest.raises(ValueError, match="Pre-attack paired trajectory"):
        _run_protocol(BadGrid(), attacked, "cpu")
    manifest = json.loads((tmp_path / "runs" / "bad_pair" / "manifest.json").read_text())
    assert manifest["status"] == "failed" and manifest["last_valid_round"] == 0
