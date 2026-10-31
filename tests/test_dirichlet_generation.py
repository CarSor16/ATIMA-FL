"""Determinism, leakage safety and non-overwrite for Dirichlet shard generator."""
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from atima_fl.runtime.dirichlet import prepare_dirichlet


@pytest.fixture
def prepared_edge(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    records = pd.DataFrame({
        "source_row_id": np.arange(250, dtype=np.int64),
        "target_id": np.repeat(np.arange(5), 50),
        "fine_label": [str(i // 50) for i in range(250)],
        "p00_pl": np.arange(250, dtype=np.float32),
    })
    records.to_parquet(root / "train_scaled.parquet", index=False)
    return root


def test_prepare_dirichlet_cover_every_row_and_never_overwrite(prepared_edge):
    target = prepare_dirichlet(prepared_edge, alpha=0.8, clients=5, seed=2026)
    assert target.name == "dirichlet_alpha_0.8"
    audit = json.loads((target / "partition_manifest.json").read_text())
    assert audit["alpha"] == 0.8
    assert audit["seed"] == 2026
    assert audit["source_rows"] == 250
    assert len(audit["source_train_sha256"]) == 64
    assignment = pd.read_parquet(target / "client_assignment.parquet")
    assert sorted(assignment.source_row_id) == list(range(250))
    assert assignment.source_row_id.is_unique
    assert set(assignment.client_id) == set(range(5))
    for cid in range(5):
        shard = pd.read_parquet(target / "clients" / f"client_{cid:02d}.parquet")
        assert len(shard) > 0
        assert set(shard.source_row_id) == set(assignment.loc[
            assignment.client_id == cid, "source_row_id"
        ])
    with pytest.raises(FileExistsError):
        prepare_dirichlet(prepared_edge, alpha=0.8, clients=5, seed=2026)


def test_prepare_dirichlet_reproducibility_and_historic_guard(prepared_edge, tmp_path):
    copied = tmp_path / "copy"
    copied.mkdir()
    shutil.copy2(prepared_edge / "train_scaled.parquet", copied / "train_scaled.parquet")
    one = prepare_dirichlet(prepared_edge, alpha=0.2, clients=5, seed=2121)
    other = prepare_dirichlet(copied, alpha=0.2, clients=5, seed=2121)
    pd.testing.assert_frame_equal(
        pd.read_parquet(one / "client_assignment.parquet"),
        pd.read_parquet(other / "client_assignment.parquet"),
    )
    with pytest.raises(ValueError, match="historic|original persisted"):
        prepare_dirichlet(prepared_edge, alpha=0.5, clients=5)
    assert not (prepared_edge / "dirichlet").exists()
    with pytest.raises(ValueError):
        prepare_dirichlet(prepared_edge, alpha=0.8, clients=300)
    with pytest.raises(FileNotFoundError):
        prepare_dirichlet(tmp_path / "nonexistent", alpha=0.8, clients=5)
