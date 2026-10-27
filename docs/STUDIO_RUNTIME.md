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
