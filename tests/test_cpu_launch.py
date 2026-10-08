from dataclasses import replace
from types import SimpleNamespace
import pytest
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.adapters.flower.launch import scheduler_allocation
from atima_fl.adapters.flower.launch import launch


def missing_slurm(*args, **kwargs):
    raise FileNotFoundError("scontrol")


def test_cpu_allocation_requires_explicit_mode_and_slurm_affinity(monkeypatch):
    monkeypatch.setattr("atima_fl.adapters.flower.launch.subprocess.run", missing_slurm)
    monkeypatch.setenv("SLURM_JOB_ID", "100")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "48")
    monkeypatch.setenv("SLURM_JOB_CPUS_PER_NODE", "48(x1)")
    monkeypatch.setenv("SLURM_JOB_NUM_NODES", "1")
    monkeypatch.setattr("atima_fl.adapters.flower.launch.os.sched_getaffinity", lambda _: set(range(48)), raising=False)
    with pytest.raises(FileNotFoundError):
        scheduler_allocation(ExperimentConfig())
    cpu = replace(ExperimentConfig(), compute_device="cpu")
    assert scheduler_allocation(cpu)["verification"] == "slurm_environment_and_process_affinity"
    monkeypatch.setenv("SLURM_JOB_CPUS_PER_NODE", "48(x2)")
    with pytest.raises(RuntimeError, match="single-node"):
        scheduler_allocation(cpu)
    monkeypatch.setenv("SLURM_JOB_CPUS_PER_NODE", "48")
    monkeypatch.setattr("atima_fl.adapters.flower.launch.os.sched_getaffinity", lambda _: set(range(16)), raising=False)
    with pytest.raises(RuntimeError, match="not granted"):
        scheduler_allocation(cpu)


def test_cpu_device_participates_in_pairing_identity():
    gpu = ExperimentConfig()
    cpu = replace(gpu, compute_device="cpu").validate()
    assert gpu.pairing_id({}) != cpu.pairing_id({})
    with pytest.raises(ValueError, match="device"):
        replace(gpu, compute_device="automatic").validate()


def test_explicit_cpu_launch_reserves_zero_ray_gpus(monkeypatch):
    recorded = {}
    monkeypatch.setattr("atima_fl.adapters.flower.launch.scheduler_allocation", lambda c: {
        "job_id": "100", "alloc_tres": {"cpu": "48"}, "scheduler_gpu_count": 0,
    })
    monkeypatch.setattr("atima_fl.adapters.flower.launch.os.sched_getaffinity", lambda _: set(range(48)), raising=False)
    monkeypatch.setattr("atima_fl.engine.data.open_dataset", lambda c: SimpleNamespace(audit=lambda: {}))
    monkeypatch.setattr("flwr.simulation.run_simulation", lambda **kwargs: recorded.update(kwargs))
    launch(replace(ExperimentConfig(), compute_device="cpu"))
    backend = recorded["backend_config"]
    assert backend["init_args"]["num_gpus"] == 0
    assert backend["client_resources"]["num_gpus"] == 0
    assert backend["init_args"]["num_cpus"] == 46
