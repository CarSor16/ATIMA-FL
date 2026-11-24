# ATIMA Web Studio

A static, local-first Results Explorer for federated intrusion-detection research.
The Python Studio and Runtime remain supported independently.

## Build and audit

From the repository root, using Python 3.12:

```sh
python scripts/build_web_studio.py _site
python -m http.server 8000 --directory _site
```

Open localhost:8000. Use a fresh output directory for each build. The builder
copies an explicit allowlist of UI assets only, not the repository, workspace,
examples, logs, environment files, SSH settings or experiment artifacts.

The Web Studio workflow checks JavaScript, the local-file reader and the shared
Results fixtures, then exercises the generated site in Chromium using synthetic
results under an ATIMA-FL subpath. Network is blocked after initial loading.
Deploy is conditional on the build and browser test passing.

## Free GitHub Pages activation

CarSor16/ATIMA-FL is public; do not change its visibility or create personal
access tokens just to publish. In repository Settings → Pages, select GitHub
Actions as the source. The workflow's automatic enablement option can only
create the site if its repository token has sufficient administrative access.
If it reports "Resource not accessible by integration", the owner must enable
Pages in Settings. No token escalation is attempted.

After activation, rerun the failed deployment (or push an updated web asset).
If the github-pages environment restricts deployment branches, permit only the
intended tested branch or merge through the usual review process. Manual
workflow dispatch becomes available when the workflow is on the default branch.

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
raw records. They are not complete reproducibility bundles. The site does not
perform SSH, schedule jobs, or generate Runtime-validated experiment plans.
Use Local Studio for the Designer and validated batch/sweep exports.

## Security and research limits

A restrictive CSP blocks network connections, forms, embedding resources,
and external scripts in the generated viewer. No analytics or remote upload
endpoint exists. GitHub necessarily serves the application's static assets.
Do not treat browser-local processing as a defense against a compromised browser,
malicious extension or altered future site build. Metadata matching is not
independent verification of the underlying model or dataset. Only compare
conditions supported by recorded identities, and use Runtime trajectory
verification for stronger paired inference.
