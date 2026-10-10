# Results workbench

The Results page reads local imported summaries through `/api/results`. Opening it does not connect to the university cluster; SSH import remains an explicit action in **Workspace results · import and refresh**.

## Select evidence

- **Single experiment**: one run and its recorded test/validation evidence.
- **A/B comparison**: filter by recorded dataset, task, model, attack or status, search identifiers, select A/B and swap their direction. Metadata shows labels/class count, completed rounds and final scores when present. **Only compatible experiments** filters B against A.
- **Paired attack vs baseline**: only backend-associated pairs that also pass the dataset audit gate. Select a class/metric and open a pair using its experiment link. Delta is attacked minus clean in this table; in A/B it is always B minus A.

Missing task, ordered audited class labels, required prepared-data fingerprints, identical test counts/support or final test metrics block quantitative comparison. Support must sum to the test population. Individual reports remain accessible; no missing provenance is reconstructed from names or inferred class counts. Different models, seeds or round caps remain explicitly descriptive comparisons, not an attack-effect claim.

## Inspect results

- Final test: accuracy, macro/weighted F1, balanced accuracy, MCC and loss. Percentage deltas use percentage points; MCC/loss use numeric differences. Classifier improvement means larger scores or lower loss. These colors do not measure adversarial success.
- Validation: raw recorded observations, selectable metric/class, A/B visibility, separate delta plot, round range, accessible point tooltips and a data table. Missing rounds/values break lines; deltas use common observations only. No smoothing.
- Per class: horizontal precision/recall/F1/support bars in recorded class order and full test metric tables. DoS is highlighted when present. The largest recorded decrease is identified without a causal claim.
- Matrices: real classes on rows, predicted classes on columns. Counts, row normalization and neutral B−A differences; zero-support normalized rows stay missing. Differences require compatible populations and matrices whose rows match recorded support.
- Support: recorded test counts only, with no inferred training or validation distributions.

View controls survive language changes, tab changes and local refresh in the current session. Native selects, keyboard tab navigation, horizontal table scrolling, light/dark themes and English/Italian use the existing dependency-free frontend. Designer navigation preserves unsaved values.

## Design and scope

Visual tokens follow the inspected [ATIMA-FL Figma Designer concept](https://www.figma.com/design/A6beVUeiNUvr1Lt0KVYhfL?node-id=2-2): navy/slate surfaces, subdued teal, compact type and restrained borders. The Figma concept is a reference; the implementation is native HTML/CSS/JavaScript, not React/Tailwind.

The scientific engine, attack/defense plugins, data preparation, SSH credentials/protocol, APIs and TOML schema are unchanged. Dataset adapters and multi-seed scientific studies remain separate work. The imported legacy runs can legitimately lack audited task metadata; this page blocks their deltas rather than inventing an audit.

## Verification

Run `python -m pytest -q`, `python -m ruff check src tests`, `node --check src/atima_fl/ui/static/app.js`, `node --check src/atima_fl/ui/static/i18n.js` and `node tests/js/results.test.cjs`. The JavaScript tests use small explicit test fixtures only; they never populate a production workspace. CI runs UI/behavior checks on Windows, Ubuntu and macOS.

## Windows update and start

```powershell
git pull --ff-only origin main
.\Avvia_ATIMA_FL.cmd -Workspace "N:\Desktop\tirocinio\Test_Cluster\Workspace_ATIMA"
```

Run these commands from the existing ATIMA-FL checkout. Close the previous GUI process before restarting on its port. The launcher preserves the selected workspace.
