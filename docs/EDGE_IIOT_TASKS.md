# Edge-IIoT classification tasks and label inspection

## Experimental provenance

The public Edge-IIoTset taxonomy describes **14 attack types plus Normal**.
The already-prepared `multiclass-logiat` representation used by ATIMA has **five
model classes**, ten ordered packets × six header features, and a retained
`fine_label` metadata column. Retaining a column does **not** establish that
all 15 reference labels occur in this particular prepared dataset.

No source parquet/CSV, split, persisted client assignment, or existing experiment
is rewritten by this feature. This is a reversible **label projection at read
time**, not regeneration of the original dataset.

| Task | Output labels | Source |
| --- | --- | --- |
| `prepared_5` (default) | Existing 5 targets | Existing `target_id` and `label_mapping.json` |
| `binary` | Normal / Attack | Verified `fine_label` |
| `family_6` | Normal + DoS/DDoS, Information Gathering, MITM, Injection, Malware | Verified `fine_label` |
| `fine_15` | Normal + 14 original attack types | Verified `fine_label` |

Taxonomy is defined in `src/atima_fl/core/label_taxonomy.py`. Labels are
matched without guesses (case-insensitive, with surrounding whitespace removed);
unrecognized values cause an explicit error. A `family_6` or `fine_15`
training run is rejected by preflight if its training split lacks an expected
output class. If the prepared dataset lacks MITM, the six-way experiment
**cannot** be represented as six classes without recovering data that contain
MITM. The 15-way case requires every original fine-grained class.

## Web designer

In the **Experiment and data** section, choose Edge-IIoT and select the
classification task. The designer updates `num_classes` and shows the
reference label names. LabelFlip source and destination become label-aware
selectors. **Inspect actual labels on this machine** reads only label columns
from the configured prepared root and current persisted partition to report:

- observed fine-label counts in training, validation and test;
- availability and missing labels for each possible task;
- output-class counts and per-client counts for the selected partition.

Inspection requires access to that directory **from the machine running the
ATIMA webapp**, not just from the browser. A Windows GUI cannot inspect a
Linux NAS path until that path is accessible to its server process. The browser
does not upload files or launch training. No new network/listening interface
is opened; the UI remains bound to localhost with its local session token.

Example **new** profile options, besides ordinary ATIMA config:

```toml
[experiment]
dataset = "edge_iiot"
dataset_root = "/verified/path/to/prepared/edge-iiot"
input_dim = 60
num_classes = 2
model = "lopez_cnn"
partition = "iid"

[experiment.dataset_params]
task = "binary"
```

For `family_6`, set `task="family_6"` and `num_classes=6`;
for `fine_15`, use `task="fine_15"` and `num_classes=15`.
The web designer sets the count automatically. Existing TOML profiles omit
`task` and therefore use `prepared_5` with `num_classes=5`. Select
`source_class` and `destination_class` for LabelFlip from the visible
task labels. Always perform dataset preflight before a real run.

## Non-IID: explicit current limitations

Existing ATIMA `iid` reads persisted `iid/` assignments. Existing
`dirichlet` reads persisted `dirichlet/` assignments with **alpha=0.5 only**.
Changing `partition` selects saved assignments; it does not synthesize
alpha=0.1 or reshard existing data. The inspection endpoint reports the
distribution for whichever persisted partition is selected. Comparing clean
and attacked configurations requires the **same** split, partition, label
projection, seed, and validated dataset hashes.

## For future datasets

Extend another dataset plugin with a `task_catalog` hook returning
`{task: {description, num_classes, class_names}}`, and an `inspect` method
on the dataset instance. Existing plugins without these optional hooks still
work. This is a small interface contract rather than forcing non-Edge-IIoT
datasets into the Edge-IIoT taxonomy.

## Source reference and validation scope

M. A. Ferrag et al., *Edge-IIoTset: A New Comprehensive Realistic Cyber
Security Dataset of IoT and IIoT Applications for Centralized and Federated
Learning*, IEEE Access (2022). Dataset taxonomy is a **public reference**,
not a verified inventory of the local prepared files.

Synthetic tests check projections, dataset audit/shard consistency, missing
MITM, unknown fine labels and backwards compatibility. Real-source inventory
and scientific GPU/Slurm execution require their respective environments.
