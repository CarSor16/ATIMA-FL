"""JSON artifact writing without optional scientific dependencies."""

from pathlib import Path
import json
import os


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + chr(10), encoding="utf-8")
    os.replace(temporary, path)
