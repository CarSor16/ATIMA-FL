"""Resolve explicitly configured dataset paths at execution time.

Web designers can export symbolic paths without having data on the local PC.
Only the machine opening the dataset (e.g. an allocated cluster job) resolves
environment references. This never searches arbitrary locations or downloads data.
"""

import os
from pathlib import Path
import re


_ENV_REFERENCE = re.compile(r"env:(ATIMA_[A-Z][A-Z0-9_]*)\Z")


def resolve_dataset_root(value):
    """Accept an explicit path or env:ATIMA_*; return an existing directory.

    No shell expansion or implicit environment-variable fallback is performed.
    The reference remains unchanged in the exported experiment TOML.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Dataset path is empty; configure a directory or env:ATIMA_DATASET_ROOT")
    if value.startswith("env:"):
        found = _ENV_REFERENCE.fullmatch(value)
        if not found:
            raise ValueError("Invalid dataset reference; use env:ATIMA_NAME with an uppercase variable name")
        variable = found.group(1)
        target = os.environ.get(variable, "").strip()
        if not target:
            raise ValueError(
                f"Dataset variable {variable} is not set on this machine. "
                "Set it to the absolute prepared-dataset directory before preflight."
            )
        value = target
        if not Path(value).is_absolute():
            raise ValueError(f"{variable} must point to an absolute prepared-dataset directory")
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Prepared dataset directory does not exist: {root}")
    return root
