"""Read-only paired campaign planning, no job or file side effects."""
import json
from urllib.request import Request, urlopen
from threading import Thread

import pytest

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.ui.campaign_preview import paired_seed_preview
from atima_fl.ui.app import create_server


def profile(**overrides):
    params = dict(
        name="ALIE_CNN_Macro5", attack="alie", rounds=30,
        attack_start=10, attack_end=30, minimum_rounds=30,
        model="lopez_cnn", batch_size=512, compute_device="cpu",
        dataset_root="env:ATIMA_EDGE_IIOT_ROOT",
        partition="iid",
    )
    params.update(overrides)
    return ExperimentConfig.from_dict(params)


def test_eleven_unique_seed_pairs_and_fixed_horizon():
    plan = paired_seed_preview(profile())
    assert plan["mode"] == "preview_only"
    assert plan["seeds"] == list(range(11))
    assert (plan["clean_runs"], plan["attack_runs"], plan["total_runs"]) == (11, 11, 22)
    assert len({item["clean_name"] for item in plan["pairs"]}) == 11
    assert len({item["attack_name"] for item in plan["pairs"]}) == 11
    for entry in plan["pairs"]:
        assert entry["paired_clean"].endswith("/" + entry["clean_name"])
        assert entry["execution_order"] == [entry["clean_name"], entry["attack_name"]]
    assert plan["rounds"] == 30
    assert plan["stopping"] == "fixed_paired_horizon"


def test_preview_is_pure_and_does_not_launch_or_export(tmp_path):
    config = profile(output_root=str(tmp_path / "results"))
    before = config.resolved()
    paired_seed_preview(config)
    assert config.resolved() == before
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("seeds", [[0, 0], [-1], [True], [], [0, "1"]])
def test_invalid_seeds_rejected(seeds):
    with pytest.raises(ValueError):
        paired_seed_preview(profile(), seeds)


def test_no_attack_or_existing_pair_rejected():
    with pytest.raises(ValueError):
        paired_seed_preview(profile(attack="none", malicious_clients=[]))
    with pytest.raises(ValueError):
        paired_seed_preview(profile(paired_clean="results/legacy_clean"))


def test_preview_api_is_session_protected_and_never_creates_plans(tmp_path):
    server = create_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = f"http://127.0.0.1:{server.server_port}"
        token = json.load(urlopen(host + "/api/catalog"))["token"]
        payload = json.dumps(profile().resolved()).encode()
        from urllib.error import HTTPError
        with pytest.raises(HTTPError) as error:
            urlopen(Request(host + "/api/campaign-preview", payload,
                            {"Content-Type": "application/json"}))
        assert error.value.code == 403
        result = json.load(urlopen(Request(
            host + "/api/campaign-preview", payload,
            {"Content-Type": "application/json", "X-ATIMA-Token": token},
        )))
        assert result["total_runs"] == 22
        assert not (tmp_path / "plans").exists()
        assert not (tmp_path / "results").exists()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize("name", ["unsafe name", "A" * 111, "campagna_à"])
def test_generated_names_must_remain_importable(name):
    with pytest.raises(ValueError, match="run names"):
        paired_seed_preview(profile(name=name))


def test_batch_export_includes_seed_matched_profiles_and_explicit_runner(tmp_path):
    from zipfile import ZipFile
    from atima_fl.engine.plans import save_seed_batch

    cfg = profile(output_root=str(tmp_path / "results"))
    root = save_seed_batch(cfg, tmp_path, [0, 10])
    manifest = json.loads((root / "campaign.json").read_text())
    assert manifest["mode"] == "paired"
    assert manifest["runs"] == 4
    assert manifest["seeds"] == [0, 10]
    with ZipFile(root / "plan.zip") as archive:
        assert "run_batch.py" in archive.namelist()
        compile(archive.read("run_batch.py"), "run_batch.py", "exec")
        for entry in manifest["entries"]:
            clean, attack = [ExperimentConfig.load(root / p) for p in entry["profiles"]]
            assert clean.seed == attack.seed == entry["seed"]
            assert clean.attack == "none"
            assert attack.attack == cfg.attack
            assert clean.minimum_rounds == attack.minimum_rounds == cfg.rounds
            assert clean.partition == attack.partition == cfg.partition
            assert attack.paired_clean == str(tmp_path / "results" / clean.name)
            assert all(p in archive.namelist() for p in entry["profiles"])
    assert not (tmp_path / "results").exists()
    with pytest.raises(FileExistsError):
        save_seed_batch(cfg, tmp_path, [0, 10])


def test_batch_export_clean_only_and_validation_before_writes(tmp_path):
    from atima_fl.engine.plans import save_seed_batch

    cfg = profile(attack="none", malicious_clients=[])
    with pytest.raises(ValueError):
        save_seed_batch(cfg, tmp_path, [0, 0])
    assert not (tmp_path / "plans").exists()
    root = save_seed_batch(cfg, tmp_path, [1, 2, 3])
    manifest = json.loads((root / "campaign.json").read_text())
    assert manifest["mode"] == "clean_only"
    assert manifest["runs"] == 3
    assert all(len(entry["profiles"]) == 1 for entry in manifest["entries"])
    assert not (tmp_path / "results").exists()


def test_sweep_shared_clean_and_distinct_model_baselines(tmp_path):
    from atima_fl.engine.plans import save_parameter_sweep

    cfg = profile(attack="update_scaling", malicious_clients=[0],
                  output_root=str(tmp_path / "results"))
    root = save_parameter_sweep(cfg, tmp_path, [0, 1], "attack_params.factor", [1, 2])
    campaign = json.loads((root / "campaign.json").read_text())
    assert campaign["runs"] == 6
    assert campaign["sweep"]["axis"] == "attack_params.factor"
    for entry in campaign["entries"]:
        clean, first, second = [ExperimentConfig.load(root / p) for p in entry["profiles"]]
        assert clean.attack == "none"
        assert first.seed == second.seed == clean.seed
        assert first.attack_params["factor"] == 1
        assert second.attack_params["factor"] == 2
        assert first.paired_clean == second.paired_clean
        assert first.paired_clean.endswith(clean.name)
    assert not (tmp_path / "results").exists()


def test_invalid_sweep_does_not_write(tmp_path):
    from atima_fl.engine.plans import save_parameter_sweep

    cfg = profile(attack="update_scaling", malicious_clients=[0])
    for axis, values in [("unknown", [1, 2]), ("attack_params.factor", [1, 1]),
                         ("malicious_count", [1, 999])]:
        with pytest.raises(ValueError):
            save_parameter_sweep(cfg, tmp_path, [0, 1], axis, values)
    assert not (tmp_path / "plans").exists()
