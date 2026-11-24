"""Build the static viewer from an explicit public asset allowlist.

No workspace files, manifests, weights, environment variables or credentials
are read or included. Only a new output directory is accepted.
"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/atima_fl/ui/static"
ASSETS = (
    "style.css", "i18n.js", "analysis-core.js", "local-results.js",
    "results.js", "fl-diagnostics.js", "web-folder.js", "web-designer.js", "web-bootstrap.js", "atima-shield-hd.png",
)
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "style-src-attr 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'none'; font-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'"
)


def replace_once(value, before, after):
    if value.count(before) != 1:
        raise ValueError(f"Shared markup changed: {before[:70]}")
    return value.replace(before, after, 1)


def build(output):
    output = Path(output)
    source = (STATIC / "index.html").read_text(encoding="utf-8")
    start = source.index('<section id="results" class="page">')
    end = source.index('<section id="guide"', start)
    results = source[start:end]
    results = replace_once(results, '<section id="results" class="page">',
                           '<section id="results" class="page active">')
    start = results.index('<details class="result-import"><summary>Workspace results')
    end = results.index('</details>', start) + len('</details>')
    results = results[:start] + results[end:]
    results = replace_once(results, 'Use Studio workspace instead', 'Forget selected files')
    results = replace_once(results, 'Source: Studio workspace.', 'Choose a local folder to begin.')
    results = replace_once(results, 'Re-select the folder to read updated files.',
                           'Re-select the folder to read updated files. No experiment contents are stored in the site.')
    results = replace_once(results, '<div class="result-actions"><label>Choose local results folder',
                           '<div class="result-actions"><button type="button" class="secondary" id="refresh-results">Re-read selected files</button><label>Choose local results folder')
    results = replace_once(results, 'Choose attacks from All_Attacks_By_Task.pdf',
                           'Choose attacks for the optional research focus')
    folder = ('<div id="web-folder-access" class="hidden card"><h3>Optional folder access</h3>'
              '<p>On supported browsers, authorize read-only folder access and refresh from disk. '
              'The saved reference is optional; file contents are never stored.</p>'
              '<div class="result-actions"><button type="button" class="secondary" id="web-folder-open">Open folder</button>'
              '<button type="button" class="secondary" id="web-folder-reconnect">Reconnect remembered folder</button>'
              '<button type="button" class="secondary" id="web-folder-refresh">Refresh authorized folder</button></div>'
              '<label class="chart-check"><input type="checkbox" id="web-folder-remember"> Remember folder reference on this device</label>'
              '<p id="web-folder-status" role="status" aria-live="polite"></p></div>')
    results = replace_once(results, '<section id="manual-comparison"', folder + '<section id="manual-comparison"')
    # Avoid claiming that imported metadata has been independently verified.
    results = results.replace('Paired attack vs baseline', 'Metadata-matched attack vs baseline')
    from atima_fl.core.configuration import ExperimentConfig
    from atima_fl.core.registry import Registry
    from atima_fl.studio.web_plan import LOCAL_FIELDS

    defaults = {k: v for k, v in asdict(ExperimentConfig()).items() if k not in LOCAL_FIELDS}
    catalog = json.dumps({"defaults": defaults, "catalog": Registry().catalog()}, ensure_ascii=True, allow_nan=False)
    designer = """<details class="card" id="web-designer"><summary>Experiment Designer · draft profiles</summary>
<p>Design a single run, multi-seed batch or parameter sweep. No data or credentials are required. Browser checks cover schema and common bounds; plugin hooks and deployment preflight require Local Studio.</p>
<div class="fields" id="web-design-fields"></div>
<div class="component-grid" id="web-design-components"></div>
<label>Ordered defense stages (JSON array of id and params)<textarea id="web-design-defenses" rows="3">[]</textarea></label>
<div class="fields">
<label>Mode<select id="web-design-mode"><option value="single">Single experiment</option><option value="batch">Multi-seed batch</option><option value="sweep">Parameter sweep</option></select></label>
<label>Campaign seeds<input id="web-design-seeds" value="0,1,2,3,4,5,6,7,8,9,10"></label>
<label>Sweep axis<select id="web-design-axis"></select></label>
<label>Sweep levels<input id="web-design-levels" placeholder="Comma-separated values"></label>
</div><div class="result-actions"><button type="button" class="secondary" id="web-design-axes">Read current sweep axes</button>
<button type="button" id="web-design-download">Download draft JSON</button></div>
<p id="web-design-status" role="status" aria-live="polite"></p>
<p>Validate and export on your PC using the matching ATIMA Studio version:</p>
<pre>atima-studio web-plan atima-web-draft.json --workspace workspace --dataset-root /path/to/prepared/data</pre>
<p>Configure cluster resources locally. No training is started.</p></details>"""
    scripts = '<script defer src="./web-catalog.js"></script>' + "".join(f'<script defer src="./{name}"></script>' for name in ASSETS if name.endswith(".js"))
    html = f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta name="description" content="Local-first research viewer for federated network intrusion detection experiments.">
<title>ATIMA Web Studio · Results Explorer</title>
<link rel="icon" href="./atima-shield-hd.png">
<link rel="stylesheet" href="./style.css"><link rel="stylesheet" href="./web.css">{scripts}
</head><body class="web-viewer"><a class="skip-link" href="#main-content">Skip to analysis</a>
<main id="main-content"><header class="web-header"><div class="web-brand">
<img src="./atima-shield-hd.png" width="64" height="64" alt="">
<div><span class="section-eyebrow">ATIMA-FL / WEB STUDIO</span><h1>Results Explorer</h1>
<p>Compare federated intrusion-detection experiments on your device.</p></div></div>
<div class="header-tools"><label>Language<select id="web-language"><option value="en">English</option><option value="it">Italiano</option></select></label>
<button type="button" class="theme-toggle" id="web-theme">Light mode</button></div></header>
<section class="card web-privacy"><h2>Local evidence, no upload</h2>
<p>Choose an experiment or campaign folder. The site serves application files only; experiment data stays in this browser tab. No backend, SSH connection, account or cookie is required.</p>
<p>Recorded summaries and metadata are not independent proof of experimental validity. Logit analysis requires a labeled test_logits.json file. Draft experiment design is available below; authoritative validation, plan export and training remain local.</p></section>
<noscript><p>JavaScript is required to read and analyze local files.</p></noscript>
{designer}
{results}
<footer class="web-footer">ATIMA-FL · Research software · Static local-first viewer</footer>
</main></body></html>"""
    output.mkdir(parents=True, exist_ok=False)
    for name in ASSETS:
        shutil.copyfile(STATIC / name, output / name)
    shutil.copyfile(STATIC / "web.css", output / "web.css")
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "web-catalog.js").write_text("const ATIMA_WEB_CATALOG = " + catalog + ";\n", encoding="utf-8")
    (output / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
