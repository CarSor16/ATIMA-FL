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
    "results.js", "fl-diagnostics.js", "web-folder.js", "web-designer.js", "web-study.js", "web-bootstrap.js", "atima-shield-hd.png",
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
    # Keep shared control IDs and analysis logic; only change the web presentation.
    results = replace_once(results, '<div class="page-intro"><div><span class="section-eyebrow">03 / ANALYTICS</span><h2>Experiment analysis</h2><p>Inspect imported evidence. Final test scores and per-round validation remain separate.</p></div></div>', '')
    results = replace_once(results, '<details class="result-import" open><summary>Local folder · browser-only analysis</summary>', '<details class="result-import web-import" open><summary>Local results folder</summary>')
    results = replace_once(results, '<div class="experiment-filters">', '<details class="web-filter-drawer"><summary>Search and filter experiments</summary><div class="experiment-filters">')
    results = replace_once(results, '<div id="experiment-choices"', '</details><div id="experiment-choices"')
    for slot in ("a", "b"):
        metadata = f'<div id="experiment-{slot}-metadata" class="selected-run"></div>'
        results = replace_once(results, metadata, '<details class="web-run-meta"><summary>Recorded configuration</summary>' + metadata + '</details>')
    results = replace_once(results, '<div id="results-workspace-panels">', '<div id="results-workspace-panels">')
    results = replace_once(results, '<section id="performance-region"', '<section id="performance-region"')
    results = replace_once(results, '<div id="performance-overview"></div>', '<p class="web-selected-label"><span>Selected experiment</span><strong id="web-selected-experiment" aria-live="polite">No experiment selected</strong></p><div id="performance-overview"></div>')
    start_seed = results.index('<section id="seed-results-panel"')
    end_seed = results.index('</section>', start_seed) + len('</section>')
    seed = results[start_seed:end_seed]
    opening = seed.index('>')
    seed = seed[:opening + 1] + '<details id="web-seed-menu"><summary><span>Multi-seed analysis</span><small id="web-seed-summary">No compatible conditions</small></summary>' + seed[opening + 1:-len('</section>')] + '</details></section>'
    seed = replace_once(seed, '<div id="seed-cohort-overview" class="seed-cohort-overview"></div>', '<details class="web-cohort-drawer"><summary>Browse all compatible conditions</summary><div id="seed-cohort-overview" class="seed-cohort-overview"></div></details>')
    results = results[:start_seed] + seed + results[end_seed:]
    results = results.replace('<div id="web-folder-access" class="hidden card"><h3>Optional folder access</h3>', '<details id="web-folder-access" class="hidden web-folder-drawer"><summary>Remember a folder (optional)</summary>')
    results = replace_once(results, '<p id="web-folder-status" role="status" aria-live="polite"></p></div>', '<p id="web-folder-status" role="status" aria-live="polite"></p></details>')
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
    study = """<details id="web-study" class="card"><summary>Study Exchange · descriptive summaries</summary>
<p>Export selected-folder results as a deliberately reduced, reviewable summary. Import multiple summary files to compare reported observations side by side. The summaries omit full training provenance, raw files and original run names; they do not establish controlled paired effects or justify pooling seeds across studies.</p>
<label>Study title<input id="web-study-title" maxlength="120" value="My study"></label>
<div class="result-actions"><button type="button" id="web-study-prepare">Prepare export preview</button><button type="button" id="web-study-download" disabled>Download reviewed study</button></div>
<details><summary>Exact export content · review before sharing</summary><pre id="web-study-preview"></pre></details>
<label>Import study summary JSON files<input type="file" id="web-study-import" accept=".json,application/json" multiple></label>
<div class="fields"><label>Metric<select id="web-study-metric"></select></label><label>Filter study and conditions<input id="web-study-filter" type="search"></label></div>
<button type="button" class="secondary" id="web-study-clear">Clear imported studies and preview</button>
<p id="web-study-status" role="status" aria-live="polite"></p><div id="web-study-output"></div></details>"""
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

<noscript><p>JavaScript is required to read and analyze local files.</p></noscript>
<nav class="web-nav" aria-label="Workspace sections"><a href="#results">Results</a><a href="#web-designer">Designer</a><a href="#web-study">Study Exchange</a><span>Local processing · no upload</span></nav>
{results}
{designer}
{study}
<details class="card web-privacy"><summary>Privacy and research limitations</summary>
<p>Choose an experiment or campaign folder. The site serves application files only; experiment data stays in this browser tab. No backend, SSH connection, account or cookie is required.</p>
<p>Recorded summaries and metadata are not independent proof of experimental validity. Logit analysis requires a labeled test_logits.json file. Draft experiment design is available below; authoritative validation, plan export and training remain local.</p></details>
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
