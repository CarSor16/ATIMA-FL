"""Physical-placement protocol fixtures; these do not exercise a real Slurm cluster."""

from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.engine.aggregation import aggregate_topology
from atima_fl.adapters.slurm.aggregation import SlurmAggregationPool, run_worker
from atima_fl.adapters.flower.launch import scheduler_allocation


def test_slurm_rejects_missing_physical_nodes(monkeypatch):
    monkeypatch.setenv("SLURM_JOB_ID", "fixture")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout="AllocTRES=cpu=48,gres/gpu=1,node=1"),
    )
    c = ExperimentConfig(servers=2, server_execution="slurm_nodes").validate()
    with pytest.raises(RuntimeError, match="one allocated node"):
        scheduler_allocation(c)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout="AllocTRES=cpu=48,gres/gpu=1,node=2"),
    )
    assert scheduler_allocation(c)["scheduler_gpu_count"] == 1


@pytest.mark.parametrize("same_host", [False, True])
def test_remote_numeric_transport_and_distinct_host_guard(tmp_path, monkeypatch, same_host):
    import atima_fl.adapters.slurm.aggregation as module

    c = ExperimentConfig(
        name="transport_fixture",
        output_root=str(tmp_path),
        clients=6,
        servers=2,
        server_execution="slurm_nodes",
    ).validate()
    (tmp_path / c.name).mkdir()
    monkeypatch.setenv("SLURM_JOB_ID", "fixture")
    commands = []

    def simulated_srun(command, **kwargs):
        assert command[:4] == ["srun", "--nodes=2", "--ntasks=2", "--ntasks-per-node=1"]
        assert "--gres=none" in command
        commands.append(command)
        directory = Path(command[-1])
        for rank in (0, 1):
            run_worker(directory, rank, hostname="same-node" if same_host else f"node-{rank}")

    monkeypatch.setattr(module.subprocess, "run", simulated_srun)
    updates = [[np.array([float(i)], dtype=np.float32)] for i in range(6)]
    pool = SlurmAggregationPool(c)
    if same_host:
        with pytest.raises(ValueError, match="distinct physical hosts"):
            aggregate_topology(updates, [1] * 6, c, pool)
        # Failed transport payloads remain available for diagnosis.
        assert list((tmp_path / c.name).glob("aggregation_step_*/request_*.npz"))
    else:
        result, audit = aggregate_topology(updates, [1] * 6, c, pool)
        np.testing.assert_array_equal(result[0], [2.5])
        assert [s["aggregation"]["worker"]["host"] for s in audit["servers"]] == [
            "node-0",
            "node-1",
        ]
        assert not list((tmp_path / c.name).glob("aggregation_step_*"))
    assert len(commands) == 1
