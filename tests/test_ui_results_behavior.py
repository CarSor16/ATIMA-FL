"""Execute dependency-free browser presentation logic under Node, also in CI."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_results_interactions_and_scientific_gates():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for functional JavaScript presentation tests")
    script = Path(__file__).parent / "js" / "results.test.cjs"
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "12 functional Results checks passed." in result.stdout
