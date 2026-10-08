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

Windows PowerShell:
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\atima ui --workspace ../ATIMA-workspace
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
separately. Current model plugins are MLP and linear classifier; the historical
CNN/transformer are preserved in previous project material, not claimed as ported.

Tests on synthetic fixtures establish software behavior. Dataset accuracy,
attack efficacy, GPU throughput and cross-platform execution require separate
verified runs. Rounds and clients are not independent statistical replicates.

## Provenance

This project evolves the independently prepared Flower baseline. Historical
Eiffel experiments remain separate and are not scientific results of ATIMA-FL.
Flower, PyTorch and cited papers retain their respective authorship/licenses.
No project license has been selected yet; public visibility alone does not grant
an open-source license.
