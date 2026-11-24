# ATIMA Web Studio

A static, local-first Results Explorer, draft Designer and Study Exchange for federated intrusion-detection research.
The Python Studio and Runtime remain supported independently.

## Build and audit

From the repository root, using Python 3.12:

```sh
python -m pip install -e .
python scripts/build_web_studio.py _site
python -m http.server 8000 --directory _site
```

Open localhost:8000. Use a fresh output directory for each build. The builder
copies an explicit allowlist of UI assets only, not the repository, workspace,
examples, logs, environment files, SSH settings or experiment artifacts.

The Web Studio workflow checks JavaScript, the local-file reader and the shared
Results fixtures, then exercises the generated site in Chromium, Firefox and WebKit using synthetic
results under an ATIMA-FL subpath. A 203-run Chromium stress case opens every individual report. WebKit is a browser-engine test, not a guarantee for every installed Safari version. Network is blocked after initial loading.
The test also exercises local draft and study-summary downloads and multi-study import. Pushes build and test only. Publication requires an explicit workflow dispatch.

## Free GitHub Pages activation

CarSor16/ATIMA-FL is public; do not change its visibility or create personal
access tokens just to publish. In repository Settings → Pages, select GitHub
Actions as the source. No personal token is needed.

Once the reviewed workflow is on the default branch, open Actions → Web Studio
→ Run workflow, choose main, and explicitly enable the publish input. The
default is false. Pushes and pull requests do not publish. The deploy job runs
only after successful build and browser tests, then the live audit checks the
served application assets and local-only behavior. Configure branch protection
for the github-pages environment as appropriate.

Expected project URL: https://carsor16.github.io/ATIMA-FL/
A successful build is not proof that Pages has been enabled or published.
Check the deployment job and the actual HTTPS page before announcing release.

## Local data and supported features

Select a directory via the browser file input. In supporting browsers the
optional read-only directory picker can refresh the authorized directory and,
with explicit opt-in, store only its handle in IndexedDB. Reconnecting requires
a user action. Forgetting clears the stored reference and in-memory evidence;
browser permissions can also be revoked in site settings. File contents are not
stored in IndexedDB, localStorage or cookies. Browser storage is origin-scoped.

The viewer supports audited result JSON summaries, automatic distinct-seed
aggregation, metadata-matched clean/attack comparisons, per-class metrics,
normalized confusion matrices, variability bands, sensitivity comparisons,
federated telemetry and local CSV export. The optional labeled test_logits.json
reader computes separate descriptive metrics; existing Runtime runs do not
automatically record raw logits. Historical incomplete evidence stays missing.

The CSV reports contain selected summary statistics, not full provenance or
raw records. They are not complete reproducibility bundles.

## Draft Designer

The build exports the built-in Registry catalog and configuration defaults as
static metadata; no workspace settings or extra plugin directory are included.
Select components, inspect their descriptions, edit parameter JSON, and choose
a single experiment, batch or parameter sweep. The browser checks registered
parameter schemas, common configuration bounds, distinct seeds and levels,
and the campaign size. It downloads a versioned draft JSON, not a validated
Runtime plan.

Use the matching local Studio installation to perform authoritative validation:

```sh
atima-studio web-plan atima-web-draft.json --workspace workspace --dataset-root /path/to/prepared/data
```

Optional local flags: --output-root and --compute-device. The converter rejects
embedded deployment settings and delegates to Core validation and the existing
plan exporters. It never starts training. The matching Runtime and dataset
preflight remain necessary. Browser checks do not reproduce every plugin hook.

## Study Exchange

Prepare a reduced summary from the current folder, inspect the exact JSON
preview and explicitly download it. The summary excludes original run names,
paths, raw records, weights, logits and deployment settings. It includes
selected scalar scientific configuration and metrics plus available global
dataset fingerprints. Titles and parameter strings should still be reviewed
before sharing; filtering is not a guarantee against arbitrary secrets.

Import up to ten study summaries (at most 1,000 observations and 8 MiB per
file). Duplicate summaries are ignored. Select a metric and filter the
paginated observations. Version 2 optionally exports SHA-256 digests of
the exact browser-local audited condition and test population metadata, and
anonymized clean-run references when the local metadata pairing gate passes.
Version 1 remains readable. Full-condition fingerprints are claims in the
imported file, not independent authentication or verification. Reduced-summary
matches stay separate from full-condition matches. Comparisons use distinct
unambiguous seeds, report each study separately, and show within-study paired
clean and attacked means, differences and sample SD only where declared
references are compatible and unambiguous. Different declared clean conditions
are explicitly flagged. The format omits full provenance and cannot establish
study independence. No cross-study seed pooling, causal inference, significance
tests, automatic publication or network transfer is performed. The summaries
remain in memory until cleared or the tab closes.

To audit a private folder after installing Playwright and Chromium locally:

```sh
python scripts/check_web_studio.py _site --results-folder /path/to/results --expected-runs 203
```

The test serves only the static asset directory, selects the private results
through the browser file input, blocks outbound requests and opens every report.
Do not put private results under _site or in the repository. The numerical
expected-run count is optional and should match the selected campaign.

The site does not perform SSH or schedule jobs.

## Security and research limits

A restrictive CSP blocks network connections, forms, embedding resources,
and external scripts in the generated viewer. No analytics or remote upload
endpoint exists. GitHub necessarily serves the application's static assets.
Do not treat browser-local processing as a defense against a compromised browser,
malicious extension or altered future site build. Metadata matching is not
independent verification of the underlying model or dataset. Only compare
conditions supported by recorded identities, and use Runtime trajectory
verification for stronger paired inference.


## Protocol cohorts and compact Results workspace

Multi-seed analysis defaults to descriptive protocol groups. Identical global
train/validation/test, feature schema, label mapping and preprocessor hashes,
class order, test supports, completed round and recorded scientific
configuration are still required. Different shard/assignment hashes,
software/runtime identity and CPU/GPU allocation settings no longer split a
protocol group automatically. Exact evidence identity is retained, and mixed
provenance is explicitly flagged. Enable Strict provenance to recover the
original exact grouping. Do not interpret mixed-provenance statistics as
fixed-shard, independently verified causal estimates. Duplicate seed IDs
remain ambiguous and are excluded. Clean/attack pairing, strict sensitivity
families and Study Exchange evidence fingerprints are not relaxed.

The static workspace places selection and performance metrics before
advanced tools, provides a compact selected-experiment label and a collapsed
multi-seed drawer with a summary. Filters, configuration details and the
complete cohort browser can be expanded when needed. The system font stack
and amber accents require no external asset requests. The local Studio
retains its original presentation.

## Focused web navigation

Results, Multi-seed, Sensitivity, Designer, Studies and Local data are separate
views within one browser tab. Switching views preserves imported evidence.
Local data provides folder selection, refresh, optional remembered directory
access, logits and reset. Results opens with an empty-state action until data is
loaded. From a compatible selected experiment, **Analyze selected condition
across seeds** opens the corresponding cohort rather than an unrelated default.
Provenance settings and the full cohort browser remain available on demand.
No changes are made to the Runtime or local Studio layout.

The descriptive protocol key also ignores the explicit CPU/CUDA device field.
Exact provenance still retains it, and metadata-matched clean/attack pairs
still require matching runtime identities. Small nonzero displayed deltas
use extra decimals when ordinary rounding would turn them into zero.
