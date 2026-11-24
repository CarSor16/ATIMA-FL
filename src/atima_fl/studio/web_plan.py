"""Convert a browser-generated draft into validated local Studio plans."""
import argparse
import json
from pathlib import Path
import re
from dataclasses import asdict

from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.plans import save_plan, save_seed_batch, save_parameter_sweep

# Deployment settings must be supplied locally, never by a shared web draft.
LOCAL_FIELDS = {"dataset_root", "output_root", "plugin_directory", "paired_clean",
                "paired_rounds", "client_servers", "server_execution", "cpu_budget",
                "compute_device", "client_cpus", "client_gpu_fraction"}


def export_draft(document, workspace, dataset_root, output_root="results", compute_device="cpu"):
    if (not isinstance(document, dict) or document.get("schema_version") != 1
            or set(document) != {"schema_version", "mode", "config", "seeds", "axis", "levels"}):
        raise ValueError("Unsupported web draft schema")
    config = document["config"]
    if not isinstance(config, dict) or set(config) - (set(asdict(ExperimentConfig())) - LOCAL_FIELDS):
        raise ValueError("Web draft contains unknown or local deployment fields")
    name = config.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", name):
        raise ValueError("Use an ASCII-safe experiment name (maximum 96 characters)")
    if not dataset_root:
        raise ValueError("Provide the dataset path on this device")
    cfg = ExperimentConfig.from_dict({
        **config, "dataset_root": str(dataset_root), "output_root": str(output_root),
        "compute_device": compute_device, "paired_clean": "", "plugin_directory": "",
    })
    mode = document["mode"]
    seeds, axis, levels = document["seeds"], document["axis"], document["levels"]
    if mode == "single" and seeds == [] and axis is None and levels == []:
        return save_plan(cfg, workspace)
    if mode == "batch" and axis is None and levels == []:
        return save_seed_batch(cfg, workspace, seeds)
    if mode == "sweep":
        return save_parameter_sweep(cfg, workspace, seeds, axis, levels)
    raise ValueError("Invalid draft mode or campaign fields")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--output-root", default="results")
    parser.add_argument("--compute-device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args(argv)
    if args.draft.stat().st_size > 1024 * 1024:
        raise ValueError("Draft exceeds 1 MiB")
    path = export_draft(json.loads(args.draft.read_text(encoding="utf-8")),
                        args.workspace, args.dataset_root, args.output_root, args.compute_device)
    print(f"Validated plan exported: {path}")
    return 0
