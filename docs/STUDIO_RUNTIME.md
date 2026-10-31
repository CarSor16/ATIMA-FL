# ATIMA Studio and Runtime boundary

This initial phase separates public entry points **without changing** the experiment
schema, the existing `atima` command, training algorithms or the generated TOML/ZIP
artifacts.

## Studio

`atima-studio ui --workspace workspace` starts the existing loopback designer.
`atima-studio validate --config experiment.toml`, `plan`, `defense-study`,
`datasets` and `catalog` are authoring and inspection commands. Studio can
run with the base installation (`pip install -e .`) and does not import Flower
as part of its command entry point.

## Runtime

`atima-runtime run experiment.toml` uses the existing Flower/Slurm integration;
`launch`, `analyze`, `compare-defenses`, `statistics` and
`defense-statistics` retain their existing behavior. Training dependencies are
still optional package extras and must be provisioned on the execution host,
for example `pip install -e '.[training,flower,analysis]'` in a compatible
isolated environment.

`atima` remains a compatibility command that exposes the union of operations.
Studio and Runtime currently share the same installable Python distribution;
these are **logical and command boundaries**, not yet two independently
publishable wheels or a portable standalone experiment generator.

## Scientific compatibility and next steps

The TOML format, ZIP contents, dataset schema, serialization, plugin contracts,
Flower protocol, Slurm assumptions, and source-identity validations remain
unchanged. A future Python exporter should consume the same validated
ExperimentConfig and package an explicitly versioned Runtime snapshot, rather
than reimplementing attacks or training.

Before creating the exporter, establish tests for Studio-only environments,
the Runtime CLI, complete clean/attacked protocol fixtures, and byte/semantic
compatibility of exported plans. Do not infer cluster GPU or Slurm compatibility
from local tests.

## Physically separate distributions (experimental)

The monorepo now also defines four wheel build targets in `packages/`. Each
target uses Hatch's explicit file mapping to ship a disjoint part of the
existing source tree. This **does not copy** the Studio implementation into the
full installation:

- `atima-core`: shared `atima_fl` root, contracts, registry, built-in
  component definitions, lightweight attack dispatch and plan exporter.
- `atima-studio`: the `studio/` and `ui/` directories, including browser assets.
- `atima-runtime`: runtime, Flower/Slurm adapters and the remaining engine.
- `atima-full`: dependency-only metapackage; it contains no application code.

Build wheel packages from a **complete monorepo checkout**, not from the
individual package directories copied elsewhere:

```bash
python -m pip install 'hatchling>=1.27,<2' build
mkdir -p dist
for part in core studio runtime full; do
  python -m build --wheel --no-isolation --outdir dist "packages/$part"
done
```

For a Studio-only environment (with Python 3.11–3.12):

```bash
python -m pip install numpy==2.2.6 'tomli-w>=1.2,<2'
python -m pip install --no-index --find-links dist atima-studio
atima-studio validate --config experiment.toml
```

For the complete *code* installation, with scientific training extras installed
separately when needed:

```bash
python -m pip install numpy==2.2.6 'tomli-w>=1.2,<2'
python -m pip install --no-index --find-links dist atima-full
```

The optional `atima-full[training]` extra adds the Runtime's PyTorch,
Flower and analysis dependencies. Cluster CUDA and scheduler compatibility
still require target-environment validation; do not install GPU libraries
blindly on a shared compute node.

**Important transition constraint:** the root `pip install -e .` remains a
legacy all-in-one package for backwards compatibility. Do not combine that
installation with the new split wheels in the same environment: they would
then have overlapping file ownership. Use a clean virtual environment for
either installation style. The split wheel builder currently relies on
the monorepo source paths, so publishing independent source distributions
and separate release pipelines remains future work.

See `.github/workflows/packages.yml` for the automated no-overlap check and
isolated-install smoke tests.


## New experiment launcher (Python + TOML)

Studio's **Export Python + TOML bundle** generates an archive containing
`experiment.toml`, `run_experiment.py`, `run_cluster.sh` and
`plan.json`. The Python launcher can be called as:

```bash
python run_experiment.py preflight --local
python run_experiment.py train --local
# In a compatible allocated Slurm job, omit --local:
python run_experiment.py preflight
python run_experiment.py train
```

The generated Python script calls the **installed matching ATIMA Runtime**.
It does *not* vendor Flower, training algorithms or malicious-attack plugins:
the generated archive is a runnable **launcher bundle**, not yet an entirely
self-contained, relocatable copy of the training stack.

## Selectable Dirichlet alpha

In Studio, select the Dirichlet partition and adjust its alpha parameter;
the same value appears in `[experiment.partition_params]` in TOML.
No shard is generated by merely editing the form. On the prepared dataset host
with Runtime training dependencies installed, create the desired non-default
alpha before preflight:

```bash
atima-runtime prepare-dirichlet --dataset-root /actual/prepared/edge-iiot --alpha 0.1 --clients 10 --seed 2026
```

The command deterministically writes `dirichlet_alpha_0.1/`, including
`clients/client_00.parquet` through `client_09.parquet`, an assignment table,
and `partition_manifest.json` with dataset hash, seed and class counts.
It rejects missing data, invalid parameters, incomplete assignments and
existing output directories; it does not rewrite train/validation/test.
A value of alpha=0.5 continues to point to the **historical**
`dirichlet/` directory. That original split is never regenerated by this
command. Before a scientific comparison, verify the original train hash and
client/class distributions; changing alpha changes the dataset partition,
which requires a newly matched clean baseline.

## Dashboard design and typography

The UI preserves a stable dark/light font stack and exposes a local-only
`Alpha Prota` display-font preference. Alpha Prota is **CC0 1.0 Universal**,
published by GGBotNet:
https://github.com/ggbotnet/fonts-cc0

The font is **not bundled** in the repository or fetched remotely at runtime:
the browser uses it only when already installed on the workstation, otherwise
it uses the same system fallback in both themes. The original transparent
ATIMA shield image is served locally. Settings and Recent Experiments use
corrected geometric icons from the same local SVG sprite. No React/shadcn
runtime was added: their block layout is a visual reference, not a frontend
framework migration.
