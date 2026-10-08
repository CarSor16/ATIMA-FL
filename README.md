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

No automatic CPU fallback. The launch verifies Slurm allocation and visible CUDA
devices. Experiments are capped at 50 rounds; clean early stopping monitors
validation macro-F1 and class recall coverage. The paired attacked run uses the
clean horizon to preserve the comparison. Numerical failure preserves the last
valid round and marks the run failed.

## Structure

```text
src/atima_fl/
  componenti/       # one file per interchangeable component
    attacchi/ modelli/ difese/ aggregatori/
    dati/ partizioni/ ottimizzatori/ perdite/ metriche/
  core/            # contracts, configuration, discovery, numerics
  engine/          # training, poisoning, aggregation, storage, analysis
  adapters/flower/ # ClientApp / ServerApp and allocated-job launcher
  ui/              # loopback web designer; no scheduler submission
examples/          # portable profiles
docs/              # plugin contract and scientific protocol
tests/             # software fixtures; not dataset benchmarks
```

Add/remove a Python file exporting `PLUGIN` in a component folder. External
components use `atima ui --plugins PATH`. No central component-name dispatch is
needed. Plugins are trusted Python code; only load code you have reviewed.
See [the component contract](docs/COMPONENTS.md) and [attack mechanisms](docs/ATTACKS.md).

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
