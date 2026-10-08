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
    no_attack = next(c for c in catalog["catalog"]["attack"] if c["id"] == "none")
    assert no_attack["title"] == "No attack"
    assert no_attack["translations"]["it"]["title"] == "Nessun attacco"
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
    assert b'<html lang="en">' in urlopen(url + "/").read()
    assert b"UI_TRANSLATIONS" in urlopen(url + "/i18n.js").read()


def test_path_escape_and_foreign_host_rejected(gui):
    _, url = gui
    with pytest.raises(HTTPError):
        urlopen(url + "/api/plans/../../outside/plan.zip")
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url + "/api/catalog", headers={"Host": "evil.example"}))
    assert caught.value.code == 403


def test_gui_validates_variable_population_and_server_groups(gui):
    _, url = gui
    catalog = json.load(urlopen(url + "/api/catalog"))
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": catalog["token"]}
    c = json.load(urlopen(url + "/api/defaults"))
    c.update(
        clients=8,
        servers=2,
        malicious_clients=[2, 5, 7],
        attack="sign_flip",
        attack_params={},
        attack_start=3,
        attack_end=5,
    )
    result = json.load(
        urlopen(Request(url + "/api/validate", json.dumps(c).encode(), headers=headers))
    )
    assert result["config"]["servers"] == 2
    assert result["config"]["malicious_clients"] == [2, 5, 7]
    c["client_servers"] = [0] * 8
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url + "/api/validate", json.dumps(c).encode(), headers=headers))
    assert caught.value.code == 422


def test_gui_exports_composed_defense_study_without_launch(gui):
    _, url = gui
    catalog = json.load(urlopen(url + "/api/catalog"))
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": catalog["token"]}
    c = json.load(urlopen(url + "/api/defaults"))
    c.update(
        name="FlipAttack_fixture",
        attack="sign_flip",
        aggregation="median",
        defenses=[
            {"id": "adaptive_clipping", "params": {}},
            {"id": "coordinate_winsorization", "params": {}},
        ],
    )
    exported = json.load(
        urlopen(Request(url + "/api/defense-study", json.dumps(c).encode(), headers=headers))
    )
    with zipfile.ZipFile(io.BytesIO(urlopen(url + exported["download"]).read())) as archive:
        study = json.loads(archive.read("study.json"))
        assert len(study["profiles"]) == 4
        protected = json.loads(archive.read("plans/FlipAttack_fixture_AttackProtected/plan.json"))
        assert [s["id"] for s in protected["config"]["defenses"]] == [
            "adaptive_clipping",
            "coordinate_winsorization",
        ]


def test_gui_task_catalog_label_dimensions_and_unavailable_local_inspection(gui):
    _, url = gui
    catalog = json.load(urlopen(url + "/api/catalog"))
    tasks = json.load(urlopen(url + "/api/dataset-tasks"))["edge_iiot"]
    assert {name: spec["num_classes"] for name, spec in tasks.items()} == {
        "prepared_5": 5, "binary": 2, "family_6": 6, "fine_15": 15
    }
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": catalog["token"]}
    initial = json.load(urlopen(url + "/api/defaults"))
    initial.update(dataset_params={"task": "binary"}, num_classes=2, name="Binary_fixture")
    checked = json.load(urlopen(Request(
        url + "/api/validate", json.dumps(initial).encode(), headers=headers
    )))
    assert checked["config"]["dataset_params"]["task"] == "binary"
    assert checked["config"]["num_classes"] == 2
    mismatch = dict(initial, num_classes=5)
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(
            url + "/api/validate", json.dumps(mismatch).encode(), headers=headers
        ))
    assert caught.value.code == 422
    # The GUI refuses to invent labels when its process cannot read the prepared root.
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(
            url + "/api/inspect-dataset", json.dumps(initial).encode(), headers=headers
        ))
    assert caught.value.code == 422
    assert b"inspect-labels" in urlopen(url + "/").read()
    assert b"selectedTaskInfo" in urlopen(url + "/app.js").read()


def test_gui_theme_toggle_brand_and_assets(gui):
    _, url = gui
    index = urlopen(url + "/").read().decode("utf-8")
    css = urlopen(url + "/style.css").read().decode("utf-8")
    app = urlopen(url + "/app.js").read().decode("utf-8")
    translation = urlopen(url + "/i18n.js").read().decode("utf-8")

    assert "Adversarial Testing Infrastructure for Model Aggregation — Federated Learning" in index
    assert 'id="theme-toggle"' in index
    assert 'id="theme-label"' in index
    assert 'id="theme-symbol"' in index
    assert 'aria-label="Dark mode"' in index
    assert 'aria-pressed=' not in index.split('id="theme-toggle"')[1].split("</button>")[0]
    assert ':root[data-theme="dark"]' in css
    assert '[data-theme="dark"] input' in css
    assert '[data-theme="dark"] .card' in css
    assert "prefers-reduced-motion" in css
    assert 'localStorage.getItem("atima-theme")' in app
    assert 'localStorage.setItem("atima-theme", theme)' in app
    assert 'document.documentElement.dataset.theme = theme' in app
    assert 'button.setAttribute("aria-label", text)' in app
    assert '"Dark mode": "Modalità scura"' in translation
    assert '"Light mode": "Modalità chiara"' in translation


def test_defense_pipeline_drag_and_keyboard_preserve_stage_export_order(gui):
    _, url = gui
    script = urlopen(url + "/app.js").read().decode("utf-8")
    page = urlopen(url + "/").read().decode("utf-8")
    translations = urlopen(url + "/i18n.js").read().decode("utf-8")
    styles = urlopen(url + "/style.css").read().decode("utf-8")
    assert 'node("button","Move up")' not in script
    assert 'node("button","Move down")' not in script
    assert 'id="defense-picker"' in page
    assert 'id="defense-components"' in page
    assert 'id="defense-order-status"' in page
    assert 'function initializeDefenses()' in script
    assert 'function setDefenseEnabled(component, enabled, initialParams=null)' in script
    assert 'grip.addEventListener("dragstart"' in script
    assert 'block.addEventListener("drop"' in script
    assert 'grip.addEventListener("keydown"' in script
    assert 'event.key==="ArrowUp"' in script
    assert 'event.key==="ArrowDown"' in script
    assert 'for(const block of $("defense-components").children)' in script
    assert 'value.defenses.push({id:component.id,params:readParams(' in script
    assert 'Drag the grip to reorder' in page
    assert '"Reorder defense": "Riordina difesa"' in translations
    assert '.defense-stage.drop-before' in styles
    assert '[data-theme="dark"] .defense-grip' in styles


def test_local_deployment_paths_prefill_without_dataset_or_remote_access(gui):
    server, url = gui
    settings = server.workspace / "deployment_defaults.json"
    payload = {
        "dataset_root": "/unavailable-on-windows/example/prepared",
        "output_root": "/cluster-only/output",
    }
    settings.write_text(json.dumps(payload), encoding="utf-8")
    defaults = json.load(urlopen(url + "/api/defaults"))
    assert defaults["dataset_root"] == payload["dataset_root"]
    assert defaults["output_root"] == payload["output_root"]
    catalog = json.load(urlopen(url + "/api/catalog"))
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": catalog["token"]}
    defaults.update(
        name="Deployment_defaults_fixture",
        defenses=[
            {"id": "coordinate_winsorization", "params": {}},
            {"id": "norm_clipping", "params": {}},
        ],
    )
    result = json.load(urlopen(Request(
        url + "/api/validate", json.dumps(defaults).encode(), headers=headers
    )))
    assert result["checks"]["dataset"] == "not_checked"
    assert result["config"]["dataset_root"] == payload["dataset_root"]
    assert [d["id"] for d in result["config"]["defenses"]] == [
        "coordinate_winsorization", "norm_clipping"
    ]
    exported = json.load(urlopen(Request(
        url + "/api/plans", json.dumps(defaults).encode(), headers=headers
    )))
    import tomllib
    with zipfile.ZipFile(io.BytesIO(urlopen(url + exported["download"]).read())) as archive:
        toml = tomllib.loads(archive.read("experiment.toml").decode("utf-8"))
    assert toml["experiment"]["dataset_root"] == payload["dataset_root"]
    assert toml["experiment"]["output_root"] == payload["output_root"]
    assert [d["id"] for d in toml["experiment"]["defenses"]] == [
        "coordinate_winsorization", "norm_clipping"
    ]
    # The designer never resolves the remote paths or downloads prepared data.
    assert not (server.workspace / "results").exists()


def test_local_deployment_path_preset_rejects_unexpected_keys(gui):
    server, url = gui
    (server.workspace / "deployment_defaults.json").write_text(
        json.dumps({"dataset_root": "/dataset", "secret": "not allowed"}),
        encoding="utf-8",
    )
    with pytest.raises(HTTPError) as caught:
        urlopen(url + "/api/defaults")
    assert caught.value.code == 422


def test_new_dataset_plugin_and_its_reference_labels_are_discovered_without_data(tmp_path):
    extra = tmp_path / "plugins"
    dataset_folder = extra / "datasets"
    dataset_folder.mkdir(parents=True)
    (dataset_folder / "toy_network.py").write_text(
        """
from atima_fl.core.contracts import Component

def catalog():
    return {
        "binary": {
            "description": "Reference labels for a fictional dataset",
            "num_classes": 2,
            "class_names": ["Normal", "Attack"],
        }
    }

PLUGIN = Component(
    id="toy_network",
    kind="dataset",
    title="Toy network traffic",
    description="Fixture plugin with reference labels, no data files.",
    hooks={"open": lambda config, params: None, "task_catalog": catalog},
)
""",
        encoding="utf-8",
    )
    server = create_server(tmp_path / "workspace", 0, plugins=extra)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        dataset_ids = {
            item["id"] for item in json.load(urlopen(base + "/api/catalog"))["catalog"]["dataset"]
        }
        assert {"edge_iiot", "toy_network"} <= dataset_ids
        tasks = json.load(urlopen(base + "/api/dataset-tasks"))
        assert tasks["toy_network"]["binary"]["class_names"] == ["Normal", "Attack"]
        assert tasks["toy_network"]["binary"]["num_classes"] == 2
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_gui_exports_symbolic_cluster_dataset_root_without_local_data(gui):
    _, url = gui
    response = json.load(urlopen(url + "/api/catalog"))
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": response["token"]}
    config = json.load(urlopen(url + "/api/defaults"))
    config.update(
        name="ClusterSymbolic_fixture",
        dataset_root="env:ATIMA_EDGE_IIOT_ROOT",
        dataset_params={"task": "binary"},
        num_classes=2,
    )
    body = json.dumps(config).encode("utf-8")
    validated = json.load(urlopen(Request(
        url + "/api/validate", body, headers=headers
    )))
    assert validated["config"]["dataset_root"] == "env:ATIMA_EDGE_IIOT_ROOT"
    assert validated["checks"]["dataset"] == "not_checked"
    created = json.load(urlopen(Request(url + "/api/plans", body, headers=headers)))
    with zipfile.ZipFile(io.BytesIO(urlopen(url + created["download"]).read())) as archive:
        toml = archive.read("experiment.toml").decode("utf-8")
        assert 'dataset_root = "env:ATIMA_EDGE_IIOT_ROOT"' in toml
    index = urlopen(url + "/").read().decode("utf-8")
    assert 'placeholder="env:ATIMA_EDGE_IIOT_ROOT"' in index
    assert "No local data is needed to export a plan." in index

def test_readable_label_selector_and_grouped_component_catalog(gui):
    _, url = gui
    html = urlopen(url + "/").read().decode("utf-8")
    script = urlopen(url + "/app.js").read().decode("utf-8")
    css = urlopen(url + "/style.css").read().decode("utf-8")
    translations = urlopen(url + "/i18n.js").read().decode("utf-8")

    assert 'id="component-list" class="catalog-accordion"' in html
    assert 'id="dataset-label-preview" class="task-label-preview"' in html
    assert "function renderComponentCatalog()" in script
    assert 'node("details",undefined,"catalog-group")' in script
    assert 'node("details",undefined,"catalog-subgroup")' in script
    assert '"defense","Defenses"' in script
    assert "function readableTaskName(task,info)" in script
    assert "function readableClassName(raw)" in script
    assert 'node("span",String(index),"label-index")' in script
    assert 'option.value=String(choice)' in script
    assert 'option.value=String(i)' in script
    assert '.task-label-pill' in css
    assert '.catalog-subgroup' in css
    assert '"Data & partitions": "Dati e partizioni"' in translations
    assert '"Reference labels · not verified against cluster data"' in translations

