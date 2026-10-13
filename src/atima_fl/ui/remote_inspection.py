"""Optional read-only SSH inspector for explicit arbitrary tabular paths."""
import json
from pathlib import Path
import re
import subprocess

from atima_fl.ui.cluster_results import connection_settings, password_ssh

_REMOTE = r'''
import csv
import gzip
import json
from pathlib import Path

root = Path(json.loads(__ATIMA_PATH__))
extensions = (".csv", ".csv.gz", ".parquet")
if root.is_symlink():
    raise ValueError("Source symlink not allowed")
if root.is_dir():
    paths = sorted(p for p in root.iterdir() if p.is_file() and not p.is_symlink()
                   and p.name.lower().endswith(extensions))
else:
    paths = [root]
if not paths or len(paths) > 64:
    raise ValueError("Expected 1..64 supported files")
columns = None
examples = {}
rows = 0
for path in paths:
    if not path.is_file() or not path.name.lower().endswith(extensions):
        raise ValueError("Unsupported or missing source file")
    if path.name.lower().endswith(".parquet"):
        try:
            import pandas as pd
        except ImportError as exc:
            raise ValueError("Remote Parquet inspection requires pandas and pyarrow") from exc
        table = pd.read_parquet(path).head(5000)
        header = [str(x) for x in table.columns]
        samples = table.astype("string").fillna("").to_dict("records")
    else:
        opener = gzip.open if path.name.lower().endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8-sig", newline="") as f:
            header_sample = f.read(4096)
        try:
            delimiter = csv.Sniffer().sniff(header_sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        with opener(path, "rt", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            header = reader.fieldnames
            samples = []
            for row in reader:
                samples.append(row)
                if len(samples) >= 5000:
                    break
    if columns is None:
        columns = header
    if header != columns:
        raise ValueError("Inconsistent source schemas")
    for row in samples:
        rows += 1
        for col in columns:
            values = examples.setdefault(col, set())
            if len(values) < 40 and row.get(col) not in (None, ""):
                values.add(str(row[col])[:120])
label_names = {"label", "labels", "attack", "attack_type", "attack_cat",
               "category", "class", "target", "outcome", "y"}
candidates = [
    {"column": col, "distinct": len(examples[col]),
     "example_values": sorted(examples[col])[:16],
     "named": col.lower().strip() in label_names,
     "reason": "recognized label column name" if col.lower().strip() in label_names
               else "low cardinality heuristic"}
    for col in columns if (col.lower().strip() in label_names or 2 <= len(examples[col]) <= 32)
]
print(json.dumps({
    "path": str(root), "files": [str(x) for x in paths], "format": "tabular",
    "sampled_rows": rows, "columns": columns, "label_candidates": candidates,
    "likely_metadata": [col for col in columns if col.lower().strip() in
                        {"src_ip", "dst_ip", "source_ip", "destination_ip",
                         "timestamp", "time", "flow_id", "id"}],
    "requires_confirmation": True,
    "note": "Read-only SSH metadata preview; no dataset bytes downloaded",
}, ensure_ascii=False))
'''


def inspect_remote(workspace, source, runner=subprocess.run):
    settings = connection_settings(workspace)
    if not settings:
        raise ValueError("Optional SSH connection not configured; use local inspection")
    if (not isinstance(source, str) or not source.startswith("/")
            or len(source) > 2048 or re.search(r"[\x00-\x1f\x7f]", source)
            or any(x in {".", ".."} for x in source.split("/"))):
        raise ValueError("Remote source must be an explicit absolute Linux path")
    script = _REMOTE.replace("__ATIMA_PATH__", repr(json.dumps(source)))
    result = password_ssh(settings, script) if runner is subprocess.run else None
    if result is None:
        try:
            reply = runner(
                ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                 "-o", "ConnectTimeout=8", "-o", "NumberOfPasswordPrompts=0",
                 "--", settings["ssh_user"] + "@" + settings["ssh_host"], "python3", "-"],
                input=script, text=True, capture_output=True, timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Remote read-only inspection failed") from exc
        if reply.returncode:
            raise ValueError("Remote metadata inspection rejected or failed; verify SSH/path/dependencies")
        result = reply.stdout
    if len(result) > 256 * 1024:
        raise ValueError("Remote response is too large")
    data = json.loads(result)
    if not isinstance(data, dict) or data.get("path") != source:
        raise ValueError("Unexpected remote inspection response")
    return data
