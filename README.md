# ATIMA-FL

**Adversarial Testing Infrastructure for Model Aggregation — Federated Learning.**

A modular experiment layer over Flower for federated learning attacks and defenses.
Design experiments in a local web interface, export validated profiles, run inside
allocated cluster jobs, and compare paired clean/attacked trajectories.

## Install

Use Python **3.12** (supported range: 3.11–3.12). Clone this repository.

```bash
git clone https://github.com/CarSor16/ATIMA-FL.git
cd ATIMA-FL
```

Windows (recommended): run `Avvia_ATIMA_FL.cmd` from the repository
(or double-click the file). The launcher checks the Git revision, verifies
Python 3.11/3.12, creates `.venv` if absent, installs the editable package
when needed, and checks the ATIMA component registry and port 8765 before
starting the local webapp. It **does not** change branches, remove files, stop
existing processes, or open a public listener.

```powershell
.\Avvia_ATIMA_FL.cmd                  # check and start the local designer
.\Avvia_ATIMA_FL.cmd -Doctor          # check/install only; do not start server
.\Avvia_ATIMA_FL.cmd -Doctor -NoInstall # read-only environment diagnostics
.\Avvia_ATIMA_FL.cmd -Port 8766       # choose another local port
```

The first launch needs Internet access to download basic dependencies. If an
existing `.venv` is broken, the launcher reports it and never deletes it.
Python may also be installed and launched manually:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m atima_fl.cli ui --workspace ..\ATIMA-workspace
```

Linux / macOS:
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/atima ui --workspace ../ATIMA-workspace
```

Open the loopback URL printed by the command. The basic installation provides
the catalog, designer, profile validation and ZIP export without PyTorch or Flower.
The local server is intended for a single user, not public hosting.

The app starts in **English** with an **Italiano** selector. Language and
Simple/Advanced switches preserve the experiment configuration.

**Simple** shows population, server count, rounds, task/model, attack choice,
malicious-client count and an inclusive attack window. **Advanced** also exposes
specific malicious IDs, client-to-server routing, component parameters,
hyperparameters, resources and stopping. Advanced values remain in effect when
hidden; review the full JSON before export.

Client and server IDs start at zero. Disabling an attack exports `attack="none"`
with no malicious clients; re-enabling restores the selected attack settings.
An attack from round 3 through 5 poisons those rounds only. From round 6 the
clients stop new poisoning; previous effects can persist in global weights.

## Edge-IIoT classification and label inspection

The Edge-IIoT dataset plugin supports the unchanged legacy `prepared_5` mapping,
plus `binary` (2 labels), `family_6` (Normal + five attack families), and
`fine_15` (Normal + fourteen attack types). The latter views are derived only
from retained, **verified** `fine_label` metadata. A missing/unknown class
causes an explicit error rather than inventing examples. The local web designer
shows the task mapping and can inspect the actual label distribution per split
and persisted client; inspection requires that the GUI process can access the
prepared dataset directory. See [Edge-IIoT task documentation](docs/EDGE_IIOT_TASKS.md).
The existing Dirichlet plugin reads **already-saved alpha=0.5 shards**, not
new arbitrary non-IID partitions.

When preparing a plan without local data, the Edge-IIoT dataset path may be
`env:ATIMA_EDGE_IIOT_ROOT` instead of a local or cluster-specific absolute path.
The exported TOML retains that reference. Inside the **cluster's allocated job**,
set `ATIMA_EDGE_IIOT_ROOT` to the verified, absolute prepared-data directory
before `bash run_cluster.sh preflight`. It is not resolved during web validation,
and does not automatically download or preprocess datasets. The older research
repository's NF-V2 CSV configurations are separate from this Edge-IIoT Parquet
plugin. See [cluster dataset sources and migration](docs/CLUSTER_DATASET_SOURCES.md).

## Aggregation topology

`servers=1` preserves ordinary central aggregation. For `servers>1`, clients
send their already-poisoned updates to assigned aggregation groups. Every
server applies the chosen aggregator and defense pipeline. A global coordinator
combines server deltas using **original sample mass**, without repeating defenses.
FedAvg composition matches central FedAvg up to floating-point rounding; robust
group aggregation generally changes the algorithm and its threat assumptions.

- `client_servers=[]`: balanced, deterministic round-robin assignment.
- `client_servers=[0,0,0,0,0,1,1,1,1,1]`: explicit assignment for ten clients.
- `server_execution="processes"`: logical aggregation servers in spawned workers
  inside the same job; Flower remains the coordinator/client message transport.
- `server_execution="slurm_nodes"`: an `srun` aggregation task on each of at least
  `servers` allocated nodes. Worker hostnames must be distinct. The shared Python
  environment, plugin paths and run directory must be accessible from every node.

Physical placement is an adapter requiring target-cluster verification. Request
the nodes, actual GPU and CPU budget in New Batch Job; profile fields do not
allocate resources. The coordinator routes deltas through shared job files; this
does not emulate independent client-to-server network links or a privacy barrier.
Slurm worker placement follows the [official srun interface](https://slurm.schedmd.com/srun.html).
Per-server input hashes, hostnames, client groups and aggregation audits are stored.
Krum/trimmed-mean requirements are checked for **every group** before launch.
Attacks retain their declared federation-wide estimation/collusion scope; they
are not automatically re-optimized against each local robust aggregator.

For software tests and analysis:
```bash
python -m pip install -e '.[training,flower,analysis,dev]'
python -m pytest
```
Use the virtual environment's Python. For GPU jobs install a CUDA-enabled
PyTorch 2.8 build compatible with the driver, following the
[official PyTorch installation instructions](https://pytorch.org/get-started/previous-versions/#v280).
The project pins Flower 1.36 and scientific dependencies in `pyproject.toml`.
Platform-specific GPU/Slurm execution must be verified on the target cluster;
Windows/macOS installation of the designer does not imply CUDA/Ray compatibility.

## Local-only cluster execution path presets

The web designer can export profiles that point to prepared data on a **remote
cluster**, without requiring the dataset on the PC. Optionally create
`deployment_defaults.json` inside the workspace passed to `atima ui --workspace`
(e.g. in the external `Workspace_ATIMA` directory) containing:

```json
{
  "dataset_root": "env:ATIMA_EDGE_IIOT_ROOT",
  "output_root": "/absolute/cluster/directory/for/results"
}
```

These fields prepopulate the web designer when it loads; they are then exported
to the TOML. The workspace file is **not part of the Git repository**, and
it must not contain credentials. You may supply an explicit absolute dataset
path instead of `env:ATIMA_EDGE_IIOT_ROOT`. No local dataset lookup is
performed during configuration or export. Before the cluster job's preflight,
set `ATIMA_EDGE_IIOT_ROOT` to the existing prepared dataset directory in
the compute environment when using the symbolic form. The preflight resolves
and audits this location; it never invents missing fine-grained classes.

### Defense pipeline interaction

Enable defense stages using the selection chips in **Defenses before
aggregation**. Selected stages appear in an ordered pipeline. Drag each
stage's grip to change execution order. With keyboard focus on the grip,
press Up/Down (or Home/End) to reorder without a mouse. Disabling a stage
removes it from the active pipeline and preserves its parameter values if
enabled again during the same session. The exported TOML `defenses` array
records the exact active stage order; disabled stages are excluded. Changing
the UI order changes the scientific preprocessing pipeline, so record it
as an experimental variable.

## Read-only cluster results synchronization

**Workspace Results** can now import run summaries directly from the university
cluster using your workstation's existing **OpenSSH** credentials. This feature
is opt-in and does not connect on startup. Put a local-only
`cluster_connection.json` in the **same ATIMA workspace** used for
`deployment_defaults.json`:

```json
{
  "ssh_host": "YOUR_REAL_CLUSTER_SSH_HOST",
  "ssh_user": "YOUR_CLUSTER_LOGIN",
  "remote_results_root": "/nas/home/gruppo-8/repo-gruppo-8/ATIMA-FL/results"
}
```

Replace the SSH hostname and username with verified login details. The results
directory above is the project's documented intended output location, not a
claim that experiment results currently exist there. This JSON must **never**
be committed to GitHub or contain passwords, tokens or private keys.

1. Check normal SSH access from Windows first (`ssh YOUR_CLUSTER_LOGIN@YOUR_REAL_CLUSTER_SSH_HOST`).
   The host key must already be trusted in your OpenSSH `known_hosts`; use
   an SSH key or an agent, not password prompts in the ATIMA app.
2. Make sure VPN / university network access is available and the cluster's
   login node permits SSH. The cluster does not need GPU allocations just
   to read result summaries, but it must be reachable.
3. Open **Workspace Results → Import summaries from cluster**. ATIMA invokes
   the local `ssh` executable with strict host-key checking and noninteractive
   authentication. It reads at most 100 run directories, never writes remotely,
   and imports only `manifest.json` and `final_metrics.json` into local
   `workspace/results/<experiment>/`. Local experiment files are not deleted.
4. **Refresh local results** reads the downloaded summary copies.

This is not a remote file browser or a mounted filesystem; it does not pull
`trajectory.h5`, client artifacts or prepared datasets. Full paired
trajectory analysis still requires importing the appropriate HDF5 artifacts
separately using an approved university transfer method. Failures show a
generic error rather than exposing SSH stderr. There is no SSH password
storage, remote command configuration, reverse connection or background poll.

## Optional stored SSH password on Windows

For password-only university SSH access, install the optional cluster packages
and let Windows Credential Manager protect the existing account password:

```powershell
cd "N:\\Desktop\\tirocinio\\Test_Cluster\\ATIMA-FL"
.\\.venv\\Scripts\\python.exe -m pip install -e '.[cluster]'
$env:ATIMA_WORKSPACE = "N:\\Desktop\\tirocinio\\Test_Cluster\\Workspace_ATIMA"
.\\.venv\\Scripts\\python.exe -m atima_fl.ui.cluster_credentials set
.\\.venv\\Scripts\\python.exe -m atima_fl.ui.cluster_credentials check
```

On Windows, `Avvia_ATIMA_FL.cmd` automatically reuses an existing
`../Workspace_ATIMA/cluster_connection.json` when
`../ATIMA-workspace/cluster_connection.json` is absent. Explicit
`-Workspace` overrides this discovery, while the optional
`ATIMA_WORKSPACE` environment variable overrides the automatic defaults.
The launcher prints its active workspace and whether the JSON exists;
the Results page also shows the exact active workspace/config path.
No credential files are copied or written during detection.

The workspace must contain `cluster_connection.json` with the verified host,
username, and read-only results directory. `set` asks for the password in
a masked terminal prompt and stores it in the signed-in Windows user's
Credential Manager vault, not in the repository, JSON or environment variables.
`delete` removes it. In the webapp, **Workspace Results → Import summaries
from cluster** automatically uses that stored credential via Paramiko if
present, otherwise retaining the original key-based OpenSSH route.

The SSH server fingerprint must already be trusted in the Windows OpenSSH
`~/.ssh/known_hosts` file. ATIMA rejects unknown SSH server host keys.
SSH password authentication may be disallowed by cluster policy. This
integration imports result summaries only: it **does not** submit Slurm jobs
or upload TOML files. Credential Manager protects at rest but processes
running as the same Windows account may access the credential.

## Workflow

1. Choose components, seed, dataset paths and resource budget in the designer.
2. Validate and export a plan. Validation checks configuration, not hardware/data.
3. In the cluster's **New Batch Job**, request a real GPU and the configured CPUs.
4. Set `ATIMA_PYTHON` to the isolated environment's Python and run
   `bash run_cluster.sh preflight`, then `bash run_cluster.sh train`.
5. Complete the clean run first; set `paired_clean` in the attacked profile.
6. Export significant results and run `atima analyze --clean CLEAN --attack ATTACK --output ANALYSIS`.
7. For independent seed pairs: `atima statistics --inputs ANALYSIS1/comparison.json ANALYSIS2/comparison.json ANALYSIS3/comparison.json --output STATISTICS`.

CPU experiments require an explicit `compute_device = "cpu"` profile. Ray then
reserves zero GPUs and all server/client operations use CPU. GPU remains the
default; missing CUDA never selects CPU automatically. If `scontrol` is absent,
CPU execution requires a single-node Slurm allocation, valid task/node CPU
environment values and sufficient process affinity; this evidence method is
recorded in the manifest. A failed scheduler query is never silently ignored.

No automatic CPU fallback. The GPU launch verifies Slurm allocation and visible CUDA
devices. Experiments are capped at 50 rounds; clean early stopping monitors
validation macro-F1 and class recall coverage. The paired attacked run uses the
clean horizon to preserve the comparison. Numerical failure preserves the last
valid round and marks the run failed.

## Structure

```text
src/atima_fl/
  components/       # one file per interchangeable component
    attacks/ models/ defenses/ aggregators/
    datasets/ partitions/ optimizers/ losses/ metrics/
  core/            # contracts, configuration, discovery, numerics
  engine/          # training, poisoning, aggregation, storage, analysis
  adapters/flower/ # ClientApp / ServerApp and allocated-job launcher
  adapters/slurm/  # physical aggregation workers in a multi-node allocation
  ui/              # loopback web designer; no scheduler submission
examples/          # portable profiles
docs/              # plugin contract and scientific protocol
tests/             # software fixtures; not dataset benchmarks
```

Add/remove a Python file exporting `PLUGIN` in a component folder. External
components use `atima ui --plugins PATH`. No central component-name dispatch is
needed. Plugins are trusted Python code; only load code you have reviewed.
See [the component contract](docs/COMPONENTS.md) and [attack mechanisms](docs/ATTACKS.md).

**Model and dataset discovery.** The registry discovers implementations in
`src/atima_fl/components/models/*.py` and `datasets/*.py`, or the corresponding
subfolders of an optional trusted plugin directory. Selecting a model's ID invokes
that file's `build` hook, while selecting a dataset's ID invokes its `open` hook
during data-dependent operations. Datasets can optionally provide `task_catalog`
to populate the UI with reference class names and dimensions; this metadata is
available even without downloaded data. It does **not** verify class presence in
real files. `dataset_root` is still the execution cluster's actual prepared-data
directory, verified by preflight. The simplified UI displays selected defense
stages in a deterministic order; stage order remains editable in an exported TOML
if a specific scientific protocol requires it.

## Select and compare defenses

Choose multiple ordered preprocessing stages in Simple mode; tune their parameters
in Advanced. Available stages are fixed L2 clipping, adaptive quantile clipping
and coordinate median/MAD bounding. Choose one aggregator: FedAvg, median, trimmed
mean, Krum, Multi-Krum or smoothed geometric median. Suggested protections come
from plugin threat/mitigation metadata and display assumptions and scientific sources.

**Export defense comparison study** prepares clean/attack runs both with and
without protection, using a declared common round cap. It does not launch training.
The CLI equivalents are `atima defense-study`, `atima compare-defenses` and
`atima defense-statistics`. Compare attacked performance, clean utility, per-class
recall and backdoor ASR where applicable; use independent matched seed quartets
for uncertainty. See [the defense protocol and commands](docs/DEFENSES.md).

## Scientific scope

Ten mechanisms: LabelFlip, ALIE, IPM, Fang, ModelReplacement/backdoor plus random
labels, feature noise, sign flip, additive Gaussian update noise and update scaling.
These are benchmark mechanisms with overlapping categories, not ten disjoint
taxonomic classes or new attack proposals. Oracle/collusion assumptions are
declared. Shared files are not a privacy barrier.

Update attacks modify trainable parameters only: model buffers such as BatchNorm
running variance retain the local values. Raw and submitted updates are audited
separately. Current model plugins are MLP, linear classifier and LopezCNN; the historical
transformer is not claimed as ported or benchmarked.

Tests on synthetic fixtures establish software behavior. Dataset accuracy,
attack efficacy, GPU throughput and cross-platform execution require separate
verified runs. Rounds and clients are not independent statistical replicates.

## Provenance

This project evolves the independently prepared Flower baseline. Historical
Eiffel experiments remain separate and are not scientific results of ATIMA-FL.
Flower, PyTorch and cited papers retain their respective authorship/licenses.
No project license has been selected yet; public visibility alone does not grant
an open-source license.


### Results dashboard and per-round import

**Results → Import results and validation histories** reads only
`manifest.json`, `final_metrics.json`, and the compact numerical summaries
from `validation_history.json` for each run. The remote read is bounded,
non-interactive and does not transfer `trajectory.h5`, client artifacts,
datasets or model weights. Old runs without validation history are still
displayed with final test metrics.

The Results dashboard includes final test score cards, per-class metrics
and confusion matrices, an overview of matched attack-vs-clean test deltas,
and interactive per-round *validation* curves (including class recall).
Baseline pairing requires complete runs with equal `pair_id`,
software/runtime identity and valid-round count; unmatched experiments
are not automatically compared. The charts show validation history,
not independent-seed statistics or test scores at every round.


### Choose two Results experiments (manual A/B)

The Results page includes independent selectors for experiment **A** and
experiment **B**. Test accuracy, Macro-F1 and other scores are displayed
side by side with deltas **B minus A** in percentage points; per-class precision,
recall and F1 are shown when class labels align. Confusion matrices appear
side by side, and validation histories can be overlaid by round. The page
warns about differences in model, task, sample count, class support, seed,
round count and pair identity. The original automatic *Paired comparisons*
table is separate: it shows **one row per attacked run** that has exactly one
verified compatible clean baseline; baseline runs are not additional rows.
Manual comparisons are descriptive and do not prove causality or statistical
significance.

### Experiment naming

The designer now enables **Auto-name from attack and model** by default,
creating names such as \`Baseline_MLP\`, \`ALIE_CNN\`, and \`LabelFlip_MLP\`.
Dates and CPU budgets are not appended. Uncheck auto-name only when a manual
name is necessary. Old experiment folders retain their original names.
Repeated trials with the same attack/model must use distinct output roots
or existing folders will conflict; **never overwrite** finished results.
