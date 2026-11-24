# Results workbench: local-first and portable by design

ATIMA's focus is network intrusion detection under federated-learning attacks.
A study is more than an individual training run: it includes the declared
conditions, replication seeds, clean references, evaluation evidence and
limitations. Existing single-run workflows and cluster execution stay separate.

## Implemented in the multi-seed workbench

- Automatic grouping of audited fixed-partition conditions, with an opt-out.
- One selected replicate per seed. Duplicate seeds require explicit selection.
- Clean/attacked comparisons on the same matched seed population.
- Campaign completeness against a user-declared seed list. This counts compatible
  completed runs, not every job ever submitted. Missing from a cohort is not
  proof that a job was never run.
- Equal-seed means of row-normalized confusion matrices. Zero-support rows are
  missing; paired matrix means use only valid matched pairs per row.
- Optional mean ± one sample standard deviation bands for observed common rounds.
  These are descriptive variability, not confidence intervals. Proportion bands
  are clipped to their valid range and gaps are not interpolated.
- Pure numerical functions in static/analysis-core.js. These have no dependence
  on DOM, network, storage, Python or SSH.

The local API still derives condition identities and baseline associations from
audited manifests. The existing Runtime CLI verifies full trajectories for
stronger paired inference.

## Future study exchange format (design proposal, not implemented)

Use a versioned, documented study bundle rather than uploading an entire ATIMA
workspace. A bundle should carry an explicit study identifier, title, declared
campaign conditions, planned seeds, run identifiers, exact scientific parameters,
dataset and partition fingerprints, software provenance, metric definitions,
class order, final metrics and selected per-round evidence.

Separate local deployment configuration (paths, SSH host/user, credentials,
plugin locations, scheduler allocation) from scientific metadata. Export only
an explicit allowlist of fields, with a preview. Do not export raw traffic,
model weights, credentials, connection files, or local paths by default.
Run names and author metadata also need a review before sharing.

Imported studies are untrusted data. Validate schema, types, sizes, class
support and identities; never execute content, overwrite local experiments or
trust supplied cohort keys as proof of scientific comparability. Namespace run
identifiers by study, detect duplicate evidence, recompute compatibility from
the underlying audited metadata where possible, and distinguish asserted
provenance from independently verified evidence. A checksum detects changes;
it does not certify the truth of a study.

## Cross-study comparison

Keep original studies distinct. Offer side-by-side comparison before pooling.
Use the same metric definitions, task and population for paired differences.
Show differences in attack parameters, model, aggregation, partition and
software explicitly. Cross-dataset comparisons can be descriptive but must not
be reported as controlled paired experiments.

## Future GitHub Pages deployment

Keep the Local Studio and Runtime supported. First extract reusable calculations
and data contracts. Then implement a browser-only adapter that reads user-chosen
study bundles or result files and uses the same scientific gates. Test parity
with the local API using identical fixtures. Only then publish a static build.

Designer support requires equivalent configuration validation and portable
export; invalid or unsupported profiles must fail closed. A static site must
never receive SSH credentials or expose the local Python backend. Online
hosting and shared public study storage are distinct features; the latter needs
explicit consent, access control, provenance and a publication policy.

No web deployment, upload, cluster execution, or cross-study pooling is enabled
by this proposal.
