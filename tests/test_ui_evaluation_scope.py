"""The Designer must be able to author a per-client ("slice") HyperFL++ test.

Before this control existed, ``evaluation_scope`` was a TOML-only field: the
exported profile always said ``shared`` and a per-client experiment could only
be built by editing the file by hand. These tests pin the whole path from the
form to the exported profile, and pin that the core rules are the ones enforced
(no second, UI-only rule set).
"""

import io
import json
import tomllib
import zipfile
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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


def _post(url, path, body, token):
    return json.load(urlopen(Request(
        url + path,
        json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-ATIMA-Token": token},
    )))


def _hyperfl_slice():
    # The Designer resolves parameters for the *selected* model, so switching from the
    # default MLP sends LópezCNN's own (empty) parameter set, not the MLP one.
    return dict(
        model="lopez_cnn",
        model_params={},
        training_method="hyperfl_plus_plus",
        evaluation_scope="slice",
        local_epochs=2,
    )


def test_designer_exposes_per_client_evaluation_control(gui):
    _, url = gui
    page = urlopen(url + "/").read().decode("utf-8")
    script = urlopen(url + "/app.js").read().decode("utf-8")
    translations = urlopen(url + "/i18n.js").read().decode("utf-8")

    control = page.split('id="evaluation_scope"', 1)
    assert len(control) == 2
    select = control[1].split("</select>", 1)[0]
    assert 'value="shared"' in select and 'value="slice"' in select
    assert 'id="training_method"' in page
    # The option is disabled for standard FedAvg instead of silently accepted.
    assert 'option[value="slice"]' in script
    assert 'training_method").value==="hyperfl_plus_plus"' in script
    assert '"Per-client evaluation": "Valutazione per client"' in translations


def test_slice_choice_survives_validate_and_export(gui):
    server, url = gui
    token = json.load(urlopen(url + "/api/catalog"))["token"]
    config = json.load(urlopen(url + "/api/defaults"))
    config.update(_hyperfl_slice())
    config["name"] = "HyperflSlice_fixture"

    checked = _post(url, "/api/validate", config, token)
    assert checked["config"]["evaluation_scope"] == "slice"
    assert checked["config"]["training_method"] == "hyperfl_plus_plus"

    created = _post(url, "/api/toml", checked["config"], token)
    exported = urlopen(url + created["download"]).read()
    assert (server.workspace / "profiles" / "HyperflSlice_fixture.toml").read_bytes() == exported
    profile = tomllib.loads(exported.decode("utf-8"))["experiment"]
    assert profile["evaluation_scope"] == "slice"
    assert profile["training_method"] == "hyperfl_plus_plus"
    assert profile["model"] == "lopez_cnn"


def test_slice_export_reaches_the_plan_bundle(gui):
    _, url = gui
    token = json.load(urlopen(url + "/api/catalog"))["token"]
    config = json.load(urlopen(url + "/api/defaults"))
    config.update(_hyperfl_slice())
    config["name"] = "HyperflSlice_fixture"
    created = _post(url, "/api/plans", config, token)
    with zipfile.ZipFile(io.BytesIO(urlopen(url + created["download"]).read())) as archive:
        profile = tomllib.loads(archive.read("experiment.toml").decode("utf-8"))["experiment"]
    assert profile["evaluation_scope"] == "slice"


def test_core_rules_are_the_only_rules_the_designer_applies(gui):
    _, url = gui
    token = json.load(urlopen(url + "/api/catalog"))["token"]
    defaults = json.load(urlopen(url + "/api/defaults"))

    shared = dict(defaults, name="Shared_fixture", evaluation_scope="shared")
    assert _post(url, "/api/validate", shared, token)["config"]["evaluation_scope"] == "shared"

    # shared unless HyperFL++ (core: "Evaluation slices require the HyperFL++ ...")
    with pytest.raises(HTTPError) as standard_slice:
        _post(url, "/api/validate", dict(defaults, name="StdSlice_fixture",
                                         evaluation_scope="slice"), token)
    assert standard_slice.value.code == 422
    assert "HyperFL++" in standard_slice.value.read().decode()

    # HyperFL++ remains LópezCNN-only with at least two local epochs, slice or not.
    with pytest.raises(HTTPError) as wrong_model:
        _post(url, "/api/validate", dict(defaults, name="MlpHyper_fixture",
                                         training_method="hyperfl_plus_plus",
                                         evaluation_scope="slice"), token)
    assert wrong_model.value.code == 422
    assert "LopezCNN" in wrong_model.value.read().decode()

    one_epoch_body = dict(defaults, **_hyperfl_slice(), name="OneEpoch_fixture")
    one_epoch_body["local_epochs"] = 1
    with pytest.raises(HTTPError) as one_epoch:
        _post(url, "/api/validate", one_epoch_body, token)
    assert one_epoch.value.code == 422
    assert "two local epochs" in one_epoch.value.read().decode()

    # An unknown scope is refused by the core, not silently coerced.
    unknown_body = dict(defaults, **_hyperfl_slice(), name="UnknownScope_fixture")
    unknown_body["evaluation_scope"] = "shard"
    with pytest.raises(HTTPError) as unknown:
        _post(url, "/api/validate", unknown_body, token)
    assert unknown.value.code == 422
    assert "shared or slice" in unknown.value.read().decode()
