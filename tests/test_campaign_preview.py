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
