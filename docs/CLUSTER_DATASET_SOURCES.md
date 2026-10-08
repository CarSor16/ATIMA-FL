# Cluster dataset sources and symbolic paths

## Provenance: older research repository

The research handoff and the older `CarSor16/eiffel_Fork_FL-` repository identify
the following **planned data-center datasets** in
`docs/DATACENTER_RUNBOOK.md`:

| Dataset | Old repository path variable | Example location in old runbook |
| --- | --- | --- |
| NF-CSE-CIC-IDS2018-v2 | `EIFFEL_CICIDS_PATH` | `/shared/datasets/NF-CSE-CIC-IDS2018-v2.csv.gz` |
| NF-UNSW-NB15-v2 | `EIFFEL_NB15_PATH` | `/shared/datasets/NF-UNSW-NB15-v2.csv.gz` |

**These are examples, not confirmed mount paths or evidence that the files
exist on the university cluster.** The handoff does not record a verified
absolute filesystem path, account, partition or shared-storage mount.

The old configurations refer to **raw NF-V2 CSV / CSV.GZ files**, using
a TensorFlow-based pipeline. Do not feed these files to the current
`edge_iiot` dataset plugin: it expects a prepared 60-feature packet-header
Parquet dataset with fixed splits and client assignments. An NF-V2 plugin
requires its own feature/schema adapter and leakage-safe preparation,
which are not implemented by the symbolic-path feature.

## What ATIMA supports today

The existing `edge_iiot` plugin reads already-prepared Edge-IIoT data
and advertises `prepared_5`, `binary`, `family_6`, and `fine_15`
reference taxonomies, **without needing the dataset on the Windows PC**.
A web profile may now store either an explicit prepared directory or:

```toml
[experiment]
dataset = "edge_iiot"
dataset_root = "env:ATIMA_EDGE_IIOT_ROOT"
num_classes = 15

[experiment.dataset_params]
task = "fine_15"
```

ATIMA leaves `dataset_root` untouched in the exported TOML and ZIP.
It only resolves this value when opening data during local inspection,
preflight or training. The reference is strict:
`env:ATIMA_<UPPERCASE_NAME>`. No implicit scanning, shell evaluation,
remote access or automatic download occurs.

For the cluster job where the experiment will run, **after establishing a
real, prepared Edge-IIoT directory**, configure:

```bash
export ATIMA_EDGE_IIOT_ROOT="/actual/verified/cluster/path/to/prepared-edge-iiot"
export ATIMA_PYTHON="/actual/cluster/atima-venv/bin/python"
bash run_cluster.sh preflight
# Only after a successful preflight:
bash run_cluster.sh train
```

The two exported profiles in a clean/attacked pair must use the **same**
symbolic reference and must resolve to the same prepared data and
persisted client assignment. `paired_clean` and `output_root` must
still be absolute cluster paths selected by the user; they are not
derived from the dataset variable.

The prepared Edge-IIoT directory must contain
`feature_schema.json`, `label_mapping.json`,
`preprocessor.json`, `manifest.json`,
`train_scaled.parquet`, `validation_scaled.parquet`,
`test_scaled.parquet` and the persisted
`iid/` or `dirichlet/` client shards and assignments.
A `fine_15` job requires verified source labels and all 15 classes
in the training split. The reference taxonomy alone does not prove this.

## What remains to integrate

1. **Locate the actual data and mounts** on the university cluster.
   Check old runbook variables first, if the old project was installed
   there, rather than assuming `/shared/datasets` exists.
2. Decide whether to run the existing prepared Edge-IIoT benchmark or
   add an **NF-V2 dataset plugin** that uses a separately audited,
   compatible preparation pipeline. These are different datasets.
3. Verify real feature schema, label taxonomy, leakage control, split
   assignments, client coverage and resource requirements with preflight.
4. Run a small clean/attacked pair before scheduling any full campaign.

The model and dataset registry already discovers plugin implementations
from `components/models/*.py` and `components/datasets/*.py`.
New datasets should expose `PLUGIN` with an `open` hook and
optionally a `task_catalog` hook for reference class names. This
schema metadata is available to the web designer without reading data.
