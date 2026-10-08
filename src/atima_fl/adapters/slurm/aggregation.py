"""Numeric, non-pickle transport for one aggregation worker per Slurm node.

Clients remain Flower actors. The coordinator routes already-submitted deltas
to assigned server tasks over the job's shared filesystem. Each Slurm rank
aggregates one group. This is not a network/privacy isolation boundary.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import numpy as np
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.numerics import check_arrays, sha256_file
from atima_fl.engine.aggregation import aggregate


def write_request(path, updates, counts, config):
    values = {
        f"client_{cid:04d}_layer_{layer:04d}": array
        for cid, update in enumerate(updates)
        for layer, array in enumerate(update)
    }
    values["config_json"] = np.array(json.dumps(config.resolved()))
    values["counts"] = np.asarray(counts, dtype=np.int64)
    values["layers"] = np.array(len(updates[0]), dtype=np.int64)
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, **values)


def run_worker(directory, rank, hostname=None):
    directory = Path(directory).resolve()
    request = directory / f"request_{rank:04d}.npz"
    input_hash = sha256_file(request)
    with np.load(request, allow_pickle=False) as file:
        config = ExperimentConfig.from_dict(json.loads(str(file["config_json"])))
        counts = file["counts"].tolist()
        layers = int(file["layers"])
        updates = [
            [file[f"client_{cid:04d}_layer_{layer:04d}"].copy() for layer in range(layers)]
            for cid in range(len(counts))
        ]
    delta, audit = aggregate(updates, counts, config)
    audit["worker"] = {
        "rank": rank,
        "host": hostname or socket.gethostname(),
        "pid": os.getpid(),
        "input_sha256": input_hash,
    }
    values = {f"layer_{i:04d}": array for i, array in enumerate(delta)}
    values["audit_json"] = np.array(json.dumps(audit, allow_nan=False))
    result = directory / f"result_{rank:04d}.npz"
    temporary = result.with_suffix(".tmp")
    with temporary.open("xb") as stream:
        np.savez_compressed(stream, **values)
    os.replace(temporary, result)


class SlurmAggregationPool:
    def __init__(self, config):
        self.config = config
        self.run = (Path(config.output_root) / config.name).resolve()

    def aggregate_many(self, tasks):
        if len(tasks) != self.config.servers or not os.environ.get("SLURM_JOB_ID"):
            raise RuntimeError("Distributed aggregation requires an allocated Slurm job")
        directory = Path(tempfile.mkdtemp(prefix="aggregation_step_", dir=self.run)).resolve()
        if not directory.is_relative_to(self.run):
            raise RuntimeError("Aggregation work directory outside the run")
        for rank, task in enumerate(tasks):
            write_request(directory / f"request_{rank:04d}.npz", *task)
        command = [
            "srun",
            f"--nodes={len(tasks)}",
            f"--ntasks={len(tasks)}",
            "--ntasks-per-node=1",
            "--cpus-per-task=1",
            "--exclusive",
            "--exact",
            "--gres=none",
            sys.executable,
            "-m",
            "atima_fl.adapters.slurm.aggregation",
            "--directory",
            str(directory),
        ]
        environment = dict(os.environ)
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            environment[key] = "1"
        subprocess.run(command, check=True, timeout=3600, env=environment)
        results = []
        hosts = set()
        for rank, (updates, _, _) in enumerate(tasks):
            result = directory / f"result_{rank:04d}.npz"
            with np.load(result, allow_pickle=False) as file:
                delta = [file[key].copy() for key in sorted(file.files) if key.startswith("layer_")]
                audit = json.loads(str(file["audit_json"]))
            worker = audit["worker"]
            if worker["rank"] != rank or worker["input_sha256"] != sha256_file(
                directory / f"request_{rank:04d}.npz"
            ):
                raise ValueError("Distributed aggregation identity/input mismatch")
            if not worker["host"] or worker["host"] in hosts:
                raise ValueError("Aggregation servers did not execute on distinct physical hosts")
            hosts.add(worker["host"])
            check_arrays(delta, updates[0])
            audit["worker"]["result_sha256"] = sha256_file(result)
            results.append((delta, audit))
        # Only generated transport payloads are removed after all hashes/roles pass.
        shutil.rmtree(directory)
        return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    rank = int(os.environ["SLURM_PROCID"])
    run_worker(args.directory, rank)


if __name__ == "__main__":
    main()
