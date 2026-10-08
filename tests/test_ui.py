import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile
import io
import pytest
from atima_fl.ui.app import create_server


@pytest.fixture
def gui(tmp_path):
    server = create_server(tmp_path, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_gui_catalog_validate_export_no_overwrite_and_token(gui):
    server, url = gui
    catalog = json.load(urlopen(url + "/api/catalog"))
    assert len(catalog["catalog"]["attack"]) == 11
    c = json.load(urlopen(url + "/api/defaults"))
    c["name"] = "Baseline_fixture"
    body = json.dumps(c).encode()
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url + "/api/plans", body, headers={"Content-Type": "application/json"}))
    assert caught.value.code == 403
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": catalog["token"]}
    checked = json.load(urlopen(Request(url + "/api/validate", body, headers=headers)))
    assert checked["checks"]["cuda"] == "not_checked"
    result = json.load(urlopen(Request(url + "/api/plans", body, headers=headers)))
    with zipfile.ZipFile(io.BytesIO(urlopen(url + result["download"]).read())) as file:
        assert set(file.namelist()) == {"experiment.toml", "run_cluster.sh", "plan.json"}
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url + "/api/plans", body, headers=headers))
    assert caught.value.code == 409
    assert not (server.workspace / "results").exists()
    assert b"parameterFields" in urlopen(url + "/app.js").read()


def test_path_escape_and_foreign_host_rejected(gui):
    _, url = gui
    with pytest.raises(HTTPError):
        urlopen(url + "/api/plans/../../outside/plan.zip")
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url + "/api/catalog", headers={"Host": "evil.example"}))
    assert caught.value.code == 403
