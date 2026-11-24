"""Real-browser smoke test for the static viewer, using synthetic evidence only."""
import json
import shutil
from pathlib import Path
import argparse
from tempfile import TemporaryDirectory
from threading import Thread
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

from playwright.sync_api import sync_playwright, expect


def fixture(seed, attack):
    keys = ("train", "validation", "test", "feature_schema.json", "label_mapping.json",
            "preprocessor.json", "assignment", "client_0", "client_1")
    config = {
        "seed": seed, "attack": attack, "attack_params": {} if attack == "none" else {"factor": 2},
        "malicious_clients": [] if attack == "none" else [0], "clients": 2, "servers": 1,
        "dataset": "edge_iiot", "dataset_params": {"task": "binary"}, "partition": "iid",
        "partition_params": {}, "model": "mlp", "model_params": {}, "rounds": 5,
        "local_epochs": 3, "aggregation": "fedavg", "aggregation_params": {}, "defenses": [],
        "optimizer": "adam", "optimizer_params": {}, "loss": "cross_entropy", "loss_params": {},
        "batch_size": 128, "learning_rate": 0.001, "attack_start": 1, "attack_end": 5,
    }
    return {"status": "complete", "last_valid_round": 5, "pair_id": f"fixture-{seed}",
            "config": config, "dataset_audit": {"task": "binary", "classes": ["benign", "dos"],
            "hashes": {k: f"fixture-{k}" for k in keys}},
            "source_identity": {"version": "fixture"}, "runtime": {"device": "cpu"}}


def write_fixture(root, seed, attack):
    directory = root / f"{attack}-{seed}"
    directory.mkdir()
    manifest = fixture(seed, attack)
    good = attack == "none"
    matrix = [[2, 0], [0, 2]] if good else [[2, 0], [2, 0]]
    test = {"samples": 4, "macro_f1": 1.0 if good else 1/3,
            "accuracy": 1.0 if good else 0.5, "confusion_matrix": matrix,
            "per_class": {
                "benign": {"support": 2, "recall": 1, "precision": 1 if good else 0.5,
                           "f1-score": 1 if good else 2/3},
                "dos": {"support": 2, "recall": 1 if good else 0,
                        "precision": 1 if good else 0, "f1-score": 1 if good else 0},
            }}
    for name, value in [("manifest.json", manifest), ("final_metrics.json", {"test": test}),
                        ("validation_history.json", [{"round": 1, "macro_f1": test["macro_f1"]},
                                                     {"round": 5, "macro_f1": test["macro_f1"]}])]:
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    if not good:
        (directory / "test_logits.json").write_text(json.dumps({
            "schema_version": 1, "split": "test", "classes": ["benign", "dos"],
            "labels": [0, 1], "logits": [[2, 0], [1, 0]],
        }), encoding="utf-8")


def check_browser(origin, root, engine='chromium', expected=4, large=False):
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        page = browser.new_page(viewport={"width": 1280, "height": 850})
        errors, requests = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda req: requests.append((req.method, req.url)))
        page.goto(origin, wait_until="networkidle")
        expect(page.locator("#local-results-status")).to_contain_text("Choose a local folder")
        assert not errors, errors
        assert all(method == "GET" and url.startswith(origin) for method, url in requests), requests
        assert "connect-src 'none'" in page.locator("meta[http-equiv=Content-Security-Policy]").get_attribute("content")
        # Block every request after the static assets have loaded.
        page.route("**/*", lambda route: route.abort())
        count = len(requests)
        page.locator("#web-designer summary").click()
        with page.expect_download() as draft_event:
            page.locator("#web-design-download").click()
        draft = json.loads(Path(draft_event.value.path()).read_text(encoding="utf-8"))
        assert draft["schema_version"] == 1 and draft["mode"] == "single"
        assert not {"dataset_root", "output_root", "plugin_directory"} & set(draft["config"])
        page.locator("#web-design-mode").select_option("batch")
        with page.expect_download() as batch_event:
            page.locator("#web-design-download").click()
        batch = json.loads(Path(batch_event.value.path()).read_text(encoding="utf-8"))
        assert batch["seeds"] == list(range(11))
        page.locator("#web-designer summary").click()
        page.locator("#local-results-folder").set_input_files(str(root))
        expect(page.locator("#local-results-status")).to_contain_text(f"{expected} experiments read locally", timeout=60000)
        expect(page.locator("#seed-analysis-output")).to_contain_text("2/2")
        expect(page.locator("#seed-analysis-output")).to_contain_text("Metadata-matched attack minus clean")
        expect(page.locator("#seed-analysis-output")).to_contain_text("Mean normalized confusion matrices")
        with page.expect_download() as event:
            page.get_by_role("button", name="Export aggregate metrics CSV").click()
        download = event.value
        assert download.suggested_filename == "atima_cohort_metrics.csv"
        report = Path(download.path()).read_text(encoding="utf-8")
        assert "Matched clean mean" in report and str(root) not in report
        # Exercise a real IndexedDB structured-cloned directory handle on this
        # secure loopback origin, without requiring an OS permission dialog.
        if page.evaluate("typeof navigator.storage?.getDirectory === 'function' && typeof window.showDirectoryPicker === 'function'"):
            assert page.evaluate("""async () => {
          const root = await navigator.storage.getDirectory();
          const dir = await root.getDirectoryHandle('fixture-folder', {create:true});
          await ATIMAFolderAccess.remember(dir);
          const saved = await ATIMAFolderAccess.recall();
          const same = await saved.isSameEntry(dir);
          await ATIMAFolderAccess.forget();
          return same && !(await ATIMAFolderAccess.recall());
        }""")
        page.locator("#web-study > summary").click()
        page.locator("#web-study-prepare").click()
        with page.expect_download() as study_event:
            page.locator("#web-study-download").click()
        summary_path = Path(study_event.value.path())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert len(summary["observations"]) == 4
        assert str(root) not in json.dumps(summary)
        first = root / "study-a.json"
        first.write_text(json.dumps(summary), encoding="utf-8")
        summary["title"] = "Second study"
        second = root / "study-b.json"
        second.write_text(json.dumps(summary), encoding="utf-8")
        page.locator("#web-study-import").set_input_files([str(first), str(second)])
        expect(page.locator("#web-study-output")).to_contain_text("2 studies")
        expect(page.locator("#web-study-output")).to_contain_text("8 matching observations")
        page.locator("#web-study-clear").click()
        page.locator("#web-study > summary").click()
        page.locator("#local-logits-panel summary").click()
        page.locator("#local-logits-analyze").click()
        expect(page.locator("#local-logits-output")).to_contain_text("50.00%")
        page.locator("#local-results-reset").click()
        expect(page.locator("#local-results-status")).to_contain_text("Choose a local folder")
        assert not [(method, url) for method, url in requests[count:] if url.startswith(("http:", "https:"))], requests[count:]
        assert not errors, errors
        assert page.evaluate("document.cookie") == ""
        # Recheck responsive layout without reading or transmitting any real data.
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        browser.close()

    print("Static viewer passed real-browser local import, aggregation, logits, reset and offline-network checks.")


def main(site, live=False, engine='chromium'):
    with TemporaryDirectory() as temp:
        root = Path(temp) / "fixtures"
        root.mkdir()
        for seed in (0, 1):
            for attack in ("none", "update_scaling"):
                write_fixture(root, seed, attack)
        if live:
            # Public application assets only. Never send fixture files to the origin.
            from urllib.request import urlopen
            from urllib.parse import urljoin

            origin = "https://carsor16.github.io/ATIMA-FL/"
            for asset in sorted(Path(site).iterdir()):
                if asset.name == ".nojekyll":
                    continue
                with urlopen(urljoin(origin, asset.name), timeout=20) as response:
                    assert response.geturl().startswith(origin)
                    assert response.read() == asset.read_bytes(), f"Deployed asset differs: {asset.name}"
            check_browser(origin, root, engine)
            print("Live HTTPS site matches the audited static build.")
            return
        www = Path(temp) / "www"
        shutil.copytree(site, www / "ATIMA-FL")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(www)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            check_browser(f"http://127.0.0.1:{server.server_port}/ATIMA-FL/", root, engine)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    main(str(args.site.resolve()), args.live, args.browser)
