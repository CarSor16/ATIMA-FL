"""Native Flower orchestration; attacks are applied exclusively in ClientApp."""

from pathlib import Path
import json
import os
import platform
import sys
import time
import h5py
import numpy as np
import torch
import flwr
from flwr.app import ArrayRecord, ConfigRecord, Message, RecordDict
from flwr.serverapp import ServerApp
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.registry import Registry
from atima_fl.core.numerics import PlateauPolicy, check_arrays, sha256_file
from atima_fl.engine.data import open_dataset
from atima_fl.engine.models import arrays, build, probabilities, metrics
from atima_fl.engine.aggregation import aggregate_topology
from atima_fl.engine.storage import RoundStorage, atomic_json, raw_path, read_raw

app = ServerApp()


def source_identity(config):
    root = Path(__file__).resolve().parents[2]
    files = [p for folder in ("core", "engine", "adapters") for p in (root / folder).rglob("*.py")]
    shared = {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(files)}
    registry = Registry(config.plugin_directory or None, fresh=True)
    selected = [
        (kind, identifier) for kind, identifier, _ in config.selections() if kind != "attack"
    ]
    selected += [("defense", stage["id"]) for stage in config.defenses]
    shared.update(
        {
            f"component/{kind}/{identifier}": registry.sources[f"{kind}/{identifier}"]
            for kind, identifier in selected
        }
    )
    return shared


def runtime_identity(device, config):
    return {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "flower": flwr.__version__,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "device": str(device),
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
        "deterministic_algorithms": True,
        "ray_client_gpu_fraction": config.client_gpu_fraction if device == "cuda" else None,
        "visible_gpu_count": torch.cuda.device_count() if device == "cuda" else 0,
    }


def exchange(grid, node_ids, config, run, round_id, before, phase, counts):
    commands = ConfigRecord(
        {
            "config_json": json.dumps(config.resolved()),
            "run_dir": str(run),
            "server-round": round_id,
            "phase": phase,
            "counts_json": json.dumps(counts),
        }
    )
    messages = [
        Message(
            content=RecordDict({"arrays": ArrayRecord(numpy_ndarrays=before), "config": commands}),
            dst_node_id=node,
            message_type="train",
        )
        for node in node_ids
    ]
    replies = list(grid.send_and_receive(messages=messages, timeout=3600))
    result = {}
    for reply in replies:
        if reply.has_error():
            raise RuntimeError(f"Flower client error: {reply.error}")
        cid = int(reply.content["metrics"]["client-id"])
        if cid in result or not 0 <= cid < config.clients:
            raise ValueError("Duplicate/out-of-range logical client")
        values = reply.content["arrays"].to_numpy_ndarrays()
        check_arrays(values, before)
        metadata = json.loads(reply.content["audit"]["metadata_json"])
        if metadata["client"] != cid or metadata["round"] != round_id:
            raise ValueError("Reply identity/round mismatch")
        if metadata["aggregation_server"] != config.server_assignment()[cid]:
            raise ValueError("Reply aggregation server differs from configured routing")
        count = int(reply.content["metrics"]["num-examples"])
        if phase == "submit" and count != counts[cid]:
            raise ValueError("Sample count changed between phases")
        result[cid] = {"values": values, "metadata": metadata, "count": count}
    if set(result) != set(range(config.clients)):
        raise ValueError("Incomplete round: all configured logical clients are required")
    return result


def read_weights(file, path):
    return [file[path][key][...] for key in sorted(file[path])]


def run_experiment(grid, config, device="cuda"):
    config.validate()
    if device != "cuda":
        raise RuntimeError(
            "Scientific experiments require CUDA; use internal software tests for CPU"
        )
    if not torch.cuda.is_available():
        raise RuntimeError("No CUDA GPU visible to ServerApp")
    from .launch import scheduler_allocation

    allocation = scheduler_allocation(config)
    if torch.cuda.device_count() != allocation["scheduler_gpu_count"]:
        raise RuntimeError("CUDA devices differ from scheduler allocation")
    if config.servers == 1:
        return _run_protocol(grid, config, device)
    if config.server_execution == "slurm_nodes":
        from atima_fl.adapters.slurm.aggregation import SlurmAggregationPool

        return _run_protocol(grid, config, device, aggregation_pool=SlurmAggregationPool(config))
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing

    with ProcessPoolExecutor(
        max_workers=config.servers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        return _run_protocol(grid, config, device, aggregation_pool=pool)


def _run_protocol(grid, config, device, aggregation_pool=None):
    """Internal entry for software fixtures; production entry enforces CUDA."""
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    config.validate()
    data = open_dataset(config)
    audit = data.audit()
    run = Path(config.output_root) / config.name
    manifest = {
        "config": config.resolved(),
        "pair_id": config.pairing_id(audit["hashes"]),
        "dataset_audit": audit,
        "source_identity": source_identity(config),
        "runtime": runtime_identity(device, config),
        "status": "running",
        "topology": {
            "aggregation_servers": config.servers,
            "client_servers": list(config.server_assignment()),
            "coordinators": 0 if config.servers == 1 else 1,
            "execution": config.server_execution if aggregation_pool else "serial_software_fixture",
            "physical_multihost_requested": config.server_execution == "slurm_nodes",
        },
    }
    manifest["scheduler_allocation"] = json.loads(os.environ.get("ATIMA_ALLOCATION_JSON", "null"))
    before = arrays(build(config))
    reference = None
    limit = config.rounds
    if config.attack != "none":
        if not config.paired_clean:
            raise ValueError("Attack requires an explicit completed paired clean run")
        clean = json.loads((Path(config.paired_clean) / "manifest.json").read_text())
        if clean.get("status") != "complete" or clean["config"]["attack"] != "none":
            raise ValueError("Paired clean run is not complete/clean")
        for key in ("pair_id", "source_identity", "runtime"):
            if clean[key] != manifest[key]:
                raise ValueError(f"Paired clean mismatch: {key}")
        limit = clean["last_valid_round"]
        if limit < config.attack_start:
            raise ValueError("Clean ended before the configured attack window")
        if config.paired_rounds and config.paired_rounds != limit:
            raise ValueError("Explicit paired round cap differs from clean run")
        reference = h5py.File(Path(config.paired_clean) / "trajectory.h5", "r")
        initial = read_weights(reference, "initial")
        if any(not np.array_equal(a, b) for a, b in zip(initial, before)):
            reference.close()
            raise ValueError("Paired initial weights differ")
        manifest["paired_rounds"] = limit
    manifest["attack_source"] = config.registry().sources[f"attack/{config.attack}"]
    run.mkdir(parents=True, exist_ok=False)
    atomic_json(run / "manifest.json", manifest)
    storage = RoundStorage(run / "trajectory.h5", manifest)
    storage.weights(storage.file.create_group("initial"), before)
    node_ids = sorted(grid.get_node_ids())
    policy = PlateauPolicy(config)
    history = []
    last_valid = 0
    try:
        if len(node_ids) != config.clients:
            raise ValueError("Flower Grid logical client count differs from configuration")
        validation = data.split("validation")
        validation_x, validation_y = validation.x, validation.y
        counts = {}
        for round_id in range(1, limit + 1):
            if source_identity(config) != manifest["source_identity"]:
                raise ValueError("Experiment code changed during training")
            if (
                Registry(config.plugin_directory or None, fresh=True).sources[
                    f"attack/{config.attack}"
                ]
                != manifest["attack_source"]
            ):
                raise ValueError("Attack implementation changed during training")
            started = time.perf_counter()
            local = exchange(grid, node_ids, config, run, round_id, before, "train", counts)
            counts = {cid: local[cid]["count"] for cid in sorted(local)}
            submitted = exchange(grid, node_ids, config, run, round_id, before, "submit", counts)
            clients = []
            for cid in sorted(local):
                raw, _, extra = read_raw(raw_path(run, round_id, cid))
                if any(not np.array_equal(a, b) for a, b in zip(raw, local[cid]["values"])):
                    raise ValueError("Stored local model differs from train reply")
                clients.append(
                    {
                        "id": cid,
                        "raw": raw,
                        "sent": submitted[cid]["values"],
                        "metadata": submitted[cid]["metadata"],
                        "extra": extra,
                    }
                )
            deltas = [[a - b for a, b in zip(client["sent"], before)] for client in clients]
            after = None
            evaluation, aggregation = {}, {}
            try:
                delta, aggregation = aggregate_topology(
                    deltas, list(counts.values()), config, aggregation_pool
                )
                after = [a + b for a, b in zip(before, delta)]
                check_arrays(after, before)
                evaluation = metrics(
                    validation_y,
                    probabilities(after, validation_x, config, device),
                    data.classes,
                    config,
                )
                if reference is not None and round_id < config.attack_start:
                    expected = read_weights(reference, f"rounds/round_{round_id:04d}/global_after")
                    if any(not np.array_equal(a, b) for a, b in zip(expected, after)):
                        raise ValueError("Pre-attack paired trajectory differs: comparison invalid")
            except Exception as error:
                storage.commit(
                    round_id, before, None, clients, {}, aggregation, valid=False, error=str(error)
                )
                raise
            storage.commit(round_id, before, after, clients, evaluation, aggregation)
            last_valid = round_id
            history.append(
                {"round": round_id, "seconds": time.perf_counter() - started, **evaluation}
            )
            atomic_json(
                run / "round_progress.json",
                {
                    "round": round_id,
                    "cap": limit,
                    "seconds_mean": float(np.mean([v["seconds"] for v in history[:3]])),
                    "estimated_remaining_seconds": float(
                        np.mean([v["seconds"] for v in history[:3]]) * (limit - round_id)
                    ),
                },
            )
            before = after
            if config.attack == "none" and policy.step(
                round_id, evaluation["macro_f1"], evaluation["recall"]
            ):
                manifest["stop_reason"] = "validation_plateau_with_class_recall_coverage"
                break
        test = data.split("test")
        test_x, test_y = test.x, test.y
        test_p = probabilities(before, test_x, config, device)
        final = {"test": metrics(test_y, test_p, data.classes, config)}
        plugin = config.registry().get("attack", config.attack)
        evaluate_attack = plugin.hooks.get("evaluate")
        if evaluate_attack:
            final["attack_metrics"] = evaluate_attack(before, test_x, test_y, config, device)
        atomic_json(run / "final_metrics.json", final)
        atomic_json(run / "validation_history.json", history)
        manifest["status"] = "complete"
    except Exception as error:
        manifest.update(status="failed", error=f"{type(error).__name__}: {error}")
        atomic_json(run / "validation_history.json", history)
        raise
    finally:
        manifest["last_valid_round"] = last_valid
        atomic_json(run / "manifest.json", manifest)
        storage.close()
        if reference is not None:
            reference.close()
    return run


@app.main()
def main(grid, context):
    config = ExperimentConfig.load(context.run_config["experiment-config"])
    run_experiment(grid, config)
