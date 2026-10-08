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
from atima_fl.components.datasets.edge_iiot import FEATURES
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


@pytest.mark.parametrize("attack_id", ["sign_flip", "model_replacement"])
def test_full_four_condition_defense_analysis_and_mismatch_guard(
    dataset, tmp_path, monkeypatch, attack_id
):
    from atima_fl.engine.analysis import compare
    from atima_fl.engine.defense_analysis import compare_defenses

    torch.set_num_threads(1)
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl_cache"))
    base = ExperimentConfig(
        name="clean_unprotected",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        rounds=2,
        minimum_rounds=2,
        paired_rounds=2,
        model_params={"hidden": [8, 4]},
        local_epochs=1,
        attack_start=2,
    ).validate()
    analyses = []
    for protected in (False, True):
        clean_config = replace(
            base,
            name=f"clean_{protected}",
            defenses=(
                {"id": "adaptive_clipping", "params": {}},
                {"id": "coordinate_winsorization", "params": {}},
            )
            if protected
            else (),
            aggregation="geometric_median" if protected else "fedavg",
        ).validate()
        clean = _run_protocol(SoftwareGrid(), clean_config, "cpu")
        attack_config = replace(
            clean_config,
            name=f"attack_{protected}",
            attack=attack_id,
            attack_params={"strength": 20.0} if attack_id == "sign_flip" else {},
            paired_clean=str(clean),
        )
        attack = _run_protocol(SoftwareGrid(), attack_config, "cpu")
        destination = tmp_path / f"analysis_{protected}"
        compare(clean, attack, destination)
        analyses.append(destination / "comparison.json")
    result = compare_defenses(*analyses, tmp_path / "defense_effect")
    assert result["attacked_test_macro_f1_recovery"] == pytest.approx(
        result["protected"]["attacked_test"]["macro_f1"]
        - result["unprotected"]["attacked_test"]["macro_f1"]
    )
    assert (tmp_path / "defense_effect/defense_effect.png").stat().st_size > 1000
    if attack_id == "model_replacement":
        assert result["backdoor_asr_reduction"] == pytest.approx(
            result["unprotected"]["attacked_attack_metrics"]["asr_all_non_target"]
            - result["protected"]["attacked_attack_metrics"]["asr_all_non_target"]
        )
    # A common seed alone is insufficient: modifying the topology invalidates attribution.
    changed = json.loads(analyses[1].read_text())
    changed["protocol"]["condition"]["servers"] = 2
    analyses[1].write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="mismatch"):
        compare_defenses(*analyses, tmp_path / "invalid")


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
        assert not meta["local_update_is_clean_counterfactual"]
        assert meta["local_training_data_altered"] == (
            attack in {"label_flip", "random_labels", "feature_noise", "model_replacement"}
        )
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


def test_hierarchical_pair_routes_poisoned_updates_and_deactivates_attack(dataset, tmp_path):
    torch.set_num_threads(1)
    c = ExperimentConfig(
        name="hierarchical_clean",
        dataset_root=str(dataset),
        output_root=str(tmp_path / "runs"),
        servers=3,
        rounds=3,
        model_params={"hidden": [8, 4]},
        local_epochs=1,
        malicious_clients=(1, 4, 7),
        attack_start=2,
        attack_end=2,
    ).validate()
    clean = _run_protocol(SoftwareGrid(), c, "cpu")
    attacked = replace(c, name="hierarchical_flip", attack="sign_flip", paired_clean=str(clean))
    run = _run_protocol(SoftwareGrid(), attacked, "cpu")
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["topology"]["aggregation_servers"] == 3
    assert manifest["status"] == "complete"
    with h5py.File(run / "trajectory.h5") as file:
        for rid in (1, 2, 3):
            root = file[f"rounds/round_{rid:04d}"]
            aggregation = json.loads(root.attrs["aggregation_json"])
            assert aggregation["servers"][1]["clients"] == [1, 4, 7]
            for cid in range(10):
                client = root[f"clients/client_{cid:02d}"]
                metadata = json.loads(client.attrs["metadata_json"])
                assert metadata["aggregation_server"] == cid % 3
                assert metadata["active"] == (rid == 2 and cid in (1, 4, 7))
                if rid != 2 or cid not in (1, 4, 7):
                    for layer in client["local_update"]:
                        np.testing.assert_array_equal(
                            client[f"local_update/{layer}"][...],
                            client[f"submitted_update/{layer}"][...],
                        )


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

    # Exercise the actual explicit CPU ClientApp callback without a CUDA mock.
    monkeypatch.setattr(module.torch.cuda, "is_available", lambda: False)

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
        compute_device="cpu",
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
