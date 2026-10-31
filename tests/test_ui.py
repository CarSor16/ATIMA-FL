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
    assert len(catalog["catalog"]["attack"]) >= 16
    assert {"none", "label_flip", "alie", "fang", "model_replacement",
            "class_withholding", "clean_label_trigger", "free_rider",
            "stale_replay", "sybil_collusion"} <= {
        plugin["id"] for plugin in catalog["catalog"]["attack"]
    }
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
        assert set(file.namelist()) == {"experiment.toml", "run_cluster.sh", "run_experiment.py", "plan.json"}
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
    app = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
    translation = urlopen(url + "/i18n.js").read().decode("utf-8")

    assert "Adversarial Testing Infrastructure for Model Attacks" in index
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
    script = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
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
    script = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
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




def test_result_dashboard_contains_safe_client_rendering_and_round_controls(gui):
    _, url = gui
    html = urlopen(url + "/").read().decode("utf-8")
    script = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
    css = urlopen(url + "/style.css").read().decode("utf-8")
    assert 'id="result-comparisons"' in html
    assert '<script defer src="/results.js"></script>' in html
    assert "function renderResults(values)" in script
    assert "function roundChart(value,baseline,manual=false,alignedClasses=true)" in script
    assert "function matrixAnalysis(first,second,compatible)" in script
    assert "function perClassAnalysis(first,second,compatible,supportOnly=false)" in script
    assert "function deltaScore(value, reference, percent=true)" in script
    assert "run.baseline_id" in script
    assert 'metricSelect.value="macro_f1"' in script
    assert "createElementNS" in script
    assert "JSON.stringify(value.metrics,null,2)" in script
    assert "innerHTML" not in script
    assert ".confusion-matrix" in css
    assert ".round-chart" in css


def test_manual_results_compare_and_auto_attack_model_names(gui):
    _, url = gui
    html = urlopen(url + "/").read().decode("utf-8")
    script = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
    css = urlopen(url + "/style.css").read().decode("utf-8")
    translations = urlopen(url + "/i18n.js").read().decode("utf-8")
    for element in ["manual-comparison-output", "compare-experiment-a",
                    "compare-experiment-b", "compare-swap", "auto-experiment-name"]:
        assert f'id="{element}"' in html
    assert 'id="auto-experiment-name" checked' in html
    assert 'defaults.name="Baseline_MLP"' in script
    assert 'function proposedExperimentName()' in script
    assert 'none:"Baseline",alie:"ALIE"' in script
    assert 'mlp:"MLP",lopez_cnn:"CNN"' in script
    assert 'if(kind==="attack"||kind==="model")updateExperimentName();' in script
    assert 'function updateManualComparison(values)' in script
    assert 'function manualWarnings(first,second)' in script
    assert 'function manualComparison(first,second)' in script
    assert 'root.append(b?roundChart(b,a,true,true):roundChart(a,null))' in script
    assert '(first.baseline_id===second.id && verifiedPair(first,byId))' in script
    assert 'function roundChart(value,baseline,manual=false,alignedClasses=true)' in script
    assert "createElementNS" in script
    assert "innerHTML" not in script
    assert ".manual-compare-controls" in css
    assert ".manual-matrix-grid" in css
    assert '"Compare any two experiments": "Confronta due esperimenti qualsiasi"' in translations



def test_manual_comparison_fails_closed_for_mismatched_dataset_metadata(gui):
    _, url = gui
    javascript = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
    index = urlopen(url + "/").read().decode("utf-8")
    assert "function manualWarnings(first,second)" in javascript
    assert '"train","validation","test","feature_schema.json"' in javascript
    assert 'ca.dataset!==cb.dataset' in javascript
    assert 'taskA!==taskB' in javascript
    assert 'if(!sameClasses)' in javascript
    assert 'if(missingHashes.length)' in javascript
    assert 'if(sameClasses&&!supportMatches)' in javascript
    assert 'if(!validation.compatible)' in javascript
    assert 'return;' in javascript.split('if(!validation.compatible)', 1)[1].split('const a=testMetrics', 1)[0]
    assert 'Comparison blocked · incompatible experiment data' in javascript
    assert 'id="manual-comparison-output"' in index



def test_shared_dynamic_design_shell_logo_accessibility_and_assets(gui):
    _, url = gui
    page = urlopen(url + "/").read().decode("utf-8")
    script = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
    styles = urlopen(url + "/style.css").read().decode("utf-8")
    translations = urlopen(url + "/i18n.js").read().decode("utf-8")
    with urlopen(url + "/brand-mark.svg") as response:
        logo = response.read().decode("utf-8")
        assert response.headers.get_content_type() == "image/svg+xml"
    assert 'viewBox="0 0 96 96"' in logo
    assert "federated clients" in logo
    assert '<span class="mark" aria-hidden="true">▲</span>' not in page
    assert 'class="brand-mark" src="/atima-original-shield.png"' in page
    assert 'rel="icon" type="image/png" href="/atima-original-shield.png"' in page
    assert 'href="#main-content"' in page
    assert 'id="page-glyph"' in page
    assert 'id="quick-new-experiment"' in page
    assert 'id="component-search"' in page
    assert 'id="results-overview"' in page
    assert 'data-page-target="results"' in page
    assert 'aria-current="page"' in page
    assert 'const PAGE_META=' in script
    assert 'function navigateTo(page,focusHeading=false)' in script
    assert 'function updateResultsOverview(values)' in script
    assert 'catalog[kind]||[]).filter(component=>' in script
    assert 'query?" "+uiText("for search")' in script
    assert 'renderComponentCatalog();' in script
    assert 'localStorage.setItem("atima-theme", theme)' in script
    assert 'const saved = localStorage.getItem("atima-theme")' in script
    assert ':root[data-theme="dark"]' in styles
    assert '.results-overview' in styles
    assert '.step-shortcuts' in styles
    assert '@media(max-width:780px)' in styles
    assert 'prefers-reduced-motion' in styles
    assert '"Search components": "Cerca componenti"' in translations


def test_shared_page_asset_access_denies_unknown_and_external_host(gui):
    _, url = gui
    with pytest.raises(HTTPError) as missing:
        urlopen(url + "/not-an-asset.svg")
    assert missing.value.code == 404
    with pytest.raises(HTTPError) as wrong_origin:
        urlopen(Request(url + "/brand-mark.svg", headers={"Host": "external.example"}))
    assert wrong_origin.value.code == 403



def test_header_language_alignment_component_spacing_and_toml_explainer(gui):
    _, url = gui
    html = urlopen(url + "/").read().decode("utf-8")
    css = urlopen(url + "/style.css").read().decode("utf-8")
    script = (urlopen(url + "/app.js").read().decode("utf-8") + "\n" + urlopen(url + "/results.js").read().decode("utf-8"))
    translations = urlopen(url + "/i18n.js").read().decode("utf-8")
    title = "Create a federated learning security experiment"
    assert f"<h2>{title}</h2>" in html
    assert '<h1 id="page-title">Dashboard</h1>' in html
    assert '<section id="designer" class="page">' in html
    assert "Build an experiment with confidence" not in html
    assert "single experiment.toml for atima run in Slurm" in html
    assert "legacy ZIP export remains available" in html
    assert "Exports experiment.toml" in html
    assert f'heading:"{title}"' in script
    assert '"Exports experiment.toml": "Esporta experiment.toml"' in translations
    assert f'"{title}": "Crea un esperimento di sicurezza per il Federated Learning"' in translations
    assert '.header-tools .language-label{' in css
    assert 'display:inline-flex;' in css.split('.header-tools .language-label{')[1].split("}", 1)[0]
    assert 'flex-direction:row;' in css.split('.header-tools .language-label{')[1].split("}", 1)[0]
    assert 'align-items:center;' in css.split('.header-tools .language-label{')[1].split("}", 1)[0]
    assert '.header-tools .language-label select{' in css
    assert 'margin:0;' in css.split('.header-tools .language-label select{')[1].split("}", 1)[0]
    assert '.catalog-subgroups{' in css
    assert 'padding:18px 20px 22px;' in css
    assert 'padding:17px 18px 20px;' in css
    assert 'grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));' in css
    assert '@media(max-width:600px)' in css

def test_single_toml_export_and_no_overwrite(gui):
    server, url = gui
    response = json.load(urlopen(url + "/api/catalog"))
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": response["token"]}
    profile = json.load(urlopen(url + "/api/defaults"))
    profile["name"] = "SingleToml_fixture"
    body = json.dumps(profile).encode()
    result = json.load(urlopen(Request(url + "/api/toml", body, headers=headers)))
    assert result["download"] == "/api/profiles/SingleToml_fixture.toml"
    downloaded = urlopen(url + result["download"]).read()
    assert (server.workspace / "profiles" / "SingleToml_fixture.toml").read_bytes() == downloaded
    import tomllib
    assert tomllib.loads(downloaded.decode())["experiment"]["name"] == profile["name"]
    with pytest.raises(HTTPError) as err:
        urlopen(Request(url + "/api/toml", body, headers=headers))
    assert err.value.code == 409


def test_unified_designer_without_hardware_resource_controls(gui):
    _, url = gui
    html = urlopen(url + "/").read().decode()
    js = urlopen(url + "/app.js").read().decode()
    for name in ("mode-simple", "mode-advanced", "compute_device", "cpu_budget",
                 "client_cpus", "client_gpu_fraction"):
        assert 'id="' + name + '"' not in html
    assert 'id="save-zip"' in html
    assert 'id="output_root"' in html and 'id="dataset_root"' in html
    assert 'action("toml")' in js


def test_result_identity_helpers_preserve_complete_audit_and_missing_values():
    from atima_fl.ui.app import _result_dataset_identity, _result_runtime_identity

    manifest = {
        "dataset_audit": {
            "task": "macro5",
            "hashes": {"train": "abc", "validation": "def", "unexpected": "ignored"},
        },
        "source_identity": {"core/file.py": "source-hash"},
        "runtime": {"python": "3.11"},
    }
    identity = _result_dataset_identity(manifest)
    assert identity["task"] == "macro5"
    assert identity["hashes"]["train"] == "abc"
    assert identity["hashes"]["validation"] == "def"
    assert identity["hashes"]["test"] is None
    assert "unexpected" not in identity["hashes"]
    assert _result_runtime_identity(manifest) == json.dumps(
        [manifest["source_identity"], manifest["runtime"]], sort_keys=True
    )
    assert _result_runtime_identity({"source_identity": {}, "runtime": {"python": "3.11"}}) is None
    assert _result_dataset_identity({})["hashes"]["test"] is None


def test_standalone_shield_logo_served_and_not_screenshot_cropped(gui):
    _, url = gui
    html = urlopen(url + "/").read().decode("utf-8")
    css = urlopen(url + "/style.css").read().decode("utf-8")
    assert '<link rel="icon" type="image/png" href="/atima-shield-transparent.png">' in html
    assert 'src="/atima-shield-transparent.png"' in html
    assert "brand-illustration.png" not in html
    assert "object-fit:contain" in css
    image = urlopen(url + "/atima-shield-transparent.png").read()
    assert image.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10)))
    # Transparent palette PNG, square with no embedded lettering.
    width = int.from_bytes(image[16:20], "big")
    height = int.from_bytes(image[20:24], "big")
    assert (width, height) == (80, 80)
    with pytest.raises(HTTPError) as caught:
        urlopen(url + "/brand-illustration.png")
    assert caught.value.code == 404


def test_dashboard_reference_layout_assets_and_real_data(gui):
    _, url = gui
    index = urlopen(url + "/").read().decode("utf-8")
    assert '<section id="dashboard" class="page active"' in index
    assert '<section id="designer" class="page">' in index
    for item in ("dash-datasets", "dash-clients", "dash-attacks", "dash-aggregators",
                 "dash-recent-body", "dash-health", "dash-settings-theme"):
        assert f'id="{item}"' in index
    assert 'data-page="dashboard"' in index
    assert 'data-page-target="designer"' in index
    assert 'data-catalog-focus="aggregator"' in index
    assert "Federated Learning" in index and "under Attack" in index
    for route, marker in (
        ("/dashboard.css", b".dash-hero"),
        ("/dashboard.js", b'json("/api/catalog")'),
        ("/federated-world.svg", b"<svg"),
    ):
        with urlopen(url + route) as response:
            assert marker in response.read()
            assert response.status == 200
    catalog = json.load(urlopen(url + "/api/catalog"))["catalog"]
    defaults = json.load(urlopen(url + "/api/defaults"))
    assert len(catalog["attack"]) >= 21
    assert defaults["clients"] > 0
    assert json.load(urlopen(url + "/api/results")) == []
    assert "exp_001" not in index
    assert "CIC-IDS2017" not in index


def test_dashboard_cc0_map_and_original_svg_icons_are_served(gui):
    from xml.etree import ElementTree as ET

    _, url = gui
    index = urlopen(url + "/").read().decode("utf-8")
    styles = urlopen(url + "/dashboard.css").read().decode("utf-8")
    sprite = urlopen(url + "/dashboard-icons.svg").read()
    map_svg = urlopen(url + "/federated-world.svg").read()
    ns = {"svg": "http://www.w3.org/2000/svg"}
    icons = ET.fromstring(sprite)
    names = {
        element.attrib["id"]
        for element in icons.findall(".//svg:symbol", ns)
    }
    assert {"dashboard", "experiments", "datasets", "attacks",
            "aggregators", "clients", "results", "visualization",
            "settings", "documentation", "shield", "play",
            "clock", "bolt", "analytics", "network"} <= names
    for name in ("dashboard", "experiments", "datasets", "attacks",
                 "aggregators", "clients", "results", "visualization",
                 "settings", "documentation"):
        assert f'href="/dashboard-icons.svg#{name}"' in index
    assert index.count('class="dash-action-svg"') == 4
    assert index.count('class="dash-stat-svg"') == 4
    assert 'class="dash-heading-icon"' in index
    assert "dash-action-svg" in styles and "dash-bullet-icon" in styles
    image = ET.fromstring(map_svg)
    assert image.attrib["width"] == "960"
    assert image.attrib["height"] == "540"
    assert image.attrib["viewBox"] == "0 10 960 540"
    assert image.find(".//svg:clipPath", ns) is not None
    assert len(image.findall(".//svg:circle", ns)) >= 100
    assert b"prefers-reduced-motion" in map_svg
    assert "federated-world.svg" in styles


def test_exported_python_launcher_uses_runtime_without_copying_training_engine(gui):
    _, url = gui
    catalog = json.load(urlopen(url + "/api/catalog"))
    headers = {"Content-Type": "application/json", "X-ATIMA-Token": catalog["token"]}
    c = json.load(urlopen(url + "/api/defaults"))
    c["name"] = "PythonRunner_fixture"
    response = json.load(urlopen(Request(
        url + "/api/plans", json.dumps(c).encode(), headers=headers
    )))
    with zipfile.ZipFile(io.BytesIO(urlopen(url + response["download"]).read())) as archive:
        files = set(archive.namelist())
        assert {"experiment.toml", "run_experiment.py", "run_cluster.sh", "plan.json"} == files
        script = archive.read("run_experiment.py").decode()
        assert "from atima_fl.runtime.api import run_profile" in script
        assert 'choices=("preflight", "train")' in script
        assert "args.local" in script
        assert 'Path(__file__).resolve().parent / "experiment.toml"' in script
        compile(script, "run_experiment.py", "exec")
