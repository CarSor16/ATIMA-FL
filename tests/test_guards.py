from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.contracts import AttackContext
from atima_fl.core.numerics import PlateauPolicy
from atima_fl.core.registry import Registry
from atima_fl.engine.attacks import poison_update, knowledge_ids
from atima_fl.engine.models import arrays, attackable_indices, build, train
from atima_fl.engine.storage import RoundStorage
from atima_fl.adapters.flower.launch import scheduler_allocation


def test_cold_discovery_is_thread_safe(tmp_path):
    folder = tmp_path / "attacchi"
    folder.mkdir()
    (folder / "slow.py").write_text(
        "import time\nfrom atima_fl.core.contracts import Component\n"
        'time.sleep(.1)\nPLUGIN=Component("slow","attack","Slow","")\n'
    )
    with ThreadPoolExecutor(4) as pool:
        plugins = list(pool.map(lambda _: Registry(tmp_path).get("attack", "slow"), range(8)))
    assert all(plugin.id == "slow" for plugin in plugins)


@pytest.mark.parametrize(
    "attack",
    ["sign_flip", "update_scaling", "gaussian_noise", "alie", "ipm", "fang", "model_replacement"],
)
def test_real_batchnorm_buffers_are_protected(tmp_path, attack):
    folder = tmp_path / "modelli"
    folder.mkdir()
    (folder / "bn.py").write_text(
        "from atima_fl.core.contracts import Component\n"
        "def build(config,params,seed):\n"
        "    import torch\n    torch.manual_seed(seed)\n"
        "    return torch.nn.Sequential(torch.nn.Linear(60,8),torch.nn.BatchNorm1d(8),torch.nn.Linear(8,5))\n"
        'PLUGIN=Component("bn_fixture","model","BN fixture","",hooks={"build":build})\n'
    )
    c = ExperimentConfig(
        model="bn_fixture",
        plugin_directory=str(tmp_path),
        attack=attack,
        attack_start=1,
        attack_params={"knowledge": "oracle"} if attack in ("ipm", "fang") else {},
    ).validate()
    model = build(c)
    g = arrays(model)
    indices = attackable_indices(c)
    local = [a.copy() for a in g]
    for i in indices:
        local[i] += np.float32(0.1)
    # Actual running variance/counter buffers differ from initialization.
    keys = list(model.state_dict())
    for i, key in enumerate(keys):
        if key.endswith("running_var"):
            local[i][:] = 0.25
        if key.endswith("num_batches_tracked"):
            local[i][...] = 3
    ctx = AttackContext(
        c,
        0,
        1,
        g,
        local,
        {cid: [a.copy() for a in local] for cid in range(10)},
        {cid: 10 for cid in range(10)},
        indices,
    )
    submitted, _ = poison_update(ctx)
    for i in set(range(len(g))) - set(indices):
        np.testing.assert_array_equal(submitted[i], local[i])
        assert submitted[i].dtype == local[i].dtype


def test_ipm_equation_and_alie_knowledge():
    g = [np.array([10.0, 20.0], dtype=np.float32)]
    raw = {cid: [g[0] + cid] for cid in range(10)}
    c = ExperimentConfig(
        attack="ipm", attack_params={"knowledge": "oracle", "ipm_epsilon": 0.5}
    ).validate()
    ctx = AttackContext(c, 0, 10, g, raw[0], raw, {i: 10 for i in range(10)}, (0,))
    sent, _ = poison_update(ctx)
    np.testing.assert_array_equal(
        sent[0], g[0] - 0.5 * np.mean([raw[i][0] - g[0] for i in range(2, 10)], axis=0)
    )
    ctx = replace(ctx, config=replace(c, attack="alie", attack_params={}).validate())
    assert knowledge_ids(ctx) == [0, 1]
    assert knowledge_ids(replace(ctx, client=2)) == [2]
    assert knowledge_ids(replace(ctx, round_id=9)) == [0]


def test_scheduler_rejects_unallocated_gpu_and_cpu(monkeypatch):
    c = ExperimentConfig()
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(RuntimeError, match="Slurm"):
        scheduler_allocation(c)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    for tres in ["cpu=48,mem=64G", "cpu=16,gres/gpu=1"]:
        monkeypatch.setattr(
            "atima_fl.adapters.flower.launch.subprocess.run",
            lambda *a, **k: SimpleNamespace(stdout="AllocTRES=" + tres),
        )
        with pytest.raises(RuntimeError, match="not granted"):
            scheduler_allocation(c)
    monkeypatch.setattr(
        "atima_fl.adapters.flower.launch.subprocess.run",
        lambda *a, **k: SimpleNamespace(stdout="AllocTRES=cpu=48,gres/gpu=1"),
    )
    assert scheduler_allocation(c)["scheduler_gpu_count"] == 1


def test_plateau_requires_class_recall_coverage():
    p = PlateauPolicy(ExperimentConfig(minimum_rounds=5, patience=2, coverage_window=2))
    assert not p.step(1, 0.5, [0.8] * 5)
    assert not p.step(4, 0.5001, [0.8] * 5)
    assert not p.step(5, 0.5001, [0.1, 0.8, 0.8, 0.8, 0.8])
    assert not p.step(6, 0.5001, [0.8] * 5)
    assert p.step(7, 0.5001, [0.8] * 5)
    with pytest.raises(ValueError):
        p.step(8, float("nan"), [0.8] * 5)


def test_numerical_failure_keeps_last_valid_round(tmp_path):
    store = RoundStorage(tmp_path / "trajectory.h5", {})
    values = [np.ones(2, dtype=np.float32)]
    store.commit(1, values, values, [], {"macro_f1": 0.5}, {})
    store.commit(2, values, None, [], {}, {}, valid=False, error="invalid predictions")
    assert store.file.attrs["last_valid_round"] == 1
    assert "global_after" not in store.file["rounds/round_0002"]
    store.close()


def test_scalar_model_buffers_can_be_persisted(tmp_path):
    store = RoundStorage(tmp_path / "scalar.h5", {})
    values = [np.ones(2, dtype=np.float32), np.array(3, dtype=np.int64)]
    store.commit(1, values, values, [], {}, {})
    assert store.file["rounds/round_0001/global_after/layer_001"][()] == 3
    store.close()


@pytest.mark.parametrize("model", ["mlp", "linear"])
@pytest.mark.parametrize("optimizer", ["adam", "sgd"])
def test_model_optimizer_training_is_seeded(model, optimizer):
    import torch

    torch.set_num_threads(1)
    c = ExperimentConfig(model=model, optimizer=optimizer, local_epochs=1)
    g = arrays(build(c))
    x = np.full((10, 60), 0.5, dtype=np.float32)
    y = np.arange(10, dtype=np.int64) % 5
    a = train(g, x, y, c, 0, 1, "cpu")
    b = train(g, x, y, c, 0, 1, "cpu")
    for av, bv in zip(a, b):
        np.testing.assert_array_equal(av, bv)
    assert any(not np.array_equal(av, gv) for av, gv in zip(a, g))
