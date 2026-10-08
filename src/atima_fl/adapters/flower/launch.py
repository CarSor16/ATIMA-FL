"""Scheduler/CUDA preflight and the pinned Flower simulation adapter."""

import json
import os
import re
import subprocess


def scheduler_allocation(config):
    job = os.environ.get("SLURM_JOB_ID")
    if not job:
        raise RuntimeError("Submit scientific training through New Batch Job in a Slurm allocation")
    try:
        result = subprocess.run(
            ["scontrol", "show", "job", "-o", job], check=True, capture_output=True, text=True
        )
    except FileNotFoundError:
        if config.compute_device != "cpu":
            raise
        task_cpus = os.environ.get("SLURM_CPUS_PER_TASK", "")
        node_cpus = os.environ.get("SLURM_JOB_CPUS_PER_NODE", "")
        nodes = os.environ.get("SLURM_JOB_NUM_NODES", os.environ.get("SLURM_NNODES", ""))
        match = re.fullmatch(r"([1-9][0-9]*)(?:\(x1\))?", node_cpus)
        if nodes != "1" or not task_cpus.isdecimal() or not match:
            raise RuntimeError("CPU launch requires a valid single-node Slurm CPU allocation")
        granted = min(int(task_cpus), int(match.group(1)))
        affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 0
        if min(granted, affinity) < config.cpu_budget:
            raise RuntimeError("Requested CPU allocation/affinity was not granted")
        return {
            "job_id": job,
            "alloc_tres": {"cpu": str(granted), "node": "1"},
            "scheduler_gpu_count": 0,
            "verification": "slurm_environment_and_process_affinity",
            "cpu_affinity_count": affinity,
            "gpu_allocation_verified": False,
        }
    match = re.search(r"\bAllocTRES=(\S+)", result.stdout)
    if not match:
        raise RuntimeError("Cannot verify scheduler allocation")
    tres = dict(item.split("=", 1) for item in match.group(1).split(",") if "=" in item)
    gpu_count = int(tres.get("gres/gpu", "0"))
    if (config.compute_device == "cuda" and gpu_count < 1) or int(tres.get("cpu", "0")) < config.cpu_budget:
        raise RuntimeError("Requested GPU/CPU allocation was not granted")
    if config.server_execution == "slurm_nodes" and int(tres.get("node", "0")) < config.servers:
        raise RuntimeError("Physical aggregation requires one allocated node per server")
    return {"job_id": job, "alloc_tres": tres, "scheduler_gpu_count": gpu_count}


def launch(config, preflight_only=False):
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    os.environ.setdefault("OMP_NUM_THREADS", str(config.client_cpus))
    config.validate()
    allocation = scheduler_allocation(config)
    os.environ["ATIMA_ALLOCATION_JSON"] = json.dumps(allocation)
    import torch

    device = config.compute_device
    if device == "cuda" and (
        not torch.cuda.is_available()
        or torch.cuda.device_count() != allocation["scheduler_gpu_count"]
    ):
        raise RuntimeError("PyTorch CUDA visibility differs from allocated scheduler GPUs")
    torch.use_deterministic_algorithms(True)
    probe = torch.eye(4, device=device) @ torch.eye(4, device=device)
    if device == "cuda":
        torch.cuda.synchronize()
    if not torch.equal(probe, torch.eye(4, device=device)):
        raise RuntimeError("Selected device operation probe failed")
    from atima_fl.engine.data import open_dataset

    audit = open_dataset(config).audit()
    print(
        json.dumps(
            {
                "scheduler": allocation,
                "cuda": torch.version.cuda,
                "device": device,
                "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
                "dataset": audit,
            },
            indent=2,
        )
    )
    if preflight_only:
        return
    from flwr.serverapp import ServerApp
    from flwr.simulation import run_simulation
    from .client import app as client_app
    from .server import run_experiment

    server = ServerApp()

    @server.main()
    def main(grid, context):
        run_experiment(grid, config)

    run_simulation(
        server_app=server,
        client_app=client_app,
        num_supernodes=config.clients,
        backend_config={
            "init_args": {
                "num_cpus": min(
                    config.cpu_budget - config.servers - 1,
                    max(1, len(os.sched_getaffinity(0)) - 2)
                    if hasattr(os, "sched_getaffinity")
                    else config.cpu_budget - config.servers - 1,
                ),
                "num_gpus": allocation["scheduler_gpu_count"] if device == "cuda" else 0,
                "include_dashboard": False,
                "object_store_memory": 512 * 1024 * 1024,
            },
            "client_resources": {
                "num_cpus": config.client_cpus,
                "num_gpus": config.client_gpu_fraction if device == "cuda" else 0,
            },
        },
    )
