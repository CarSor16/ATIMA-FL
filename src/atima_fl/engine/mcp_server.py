"""A small read-only MCP server so an agent can inspect ATIMA runs without writing code.

Design notes that matter in practice:

- **No dependency.** The protocol used here is JSON-RPC 2.0 over stdio, which is a few hundred
  lines; adding an SDK to the training environment would be one more pinned package to keep in sync
  with `requirements.lock.txt`.
- **Read-only.** Every tool reads files that a run already wrote. Nothing trains, nothing writes
  into a run directory: an agent poking at a campaign cannot damage an experiment.
- **Testable core.** `handle()` takes a decoded request and returns a decoded response, so the tests
  exercise the same code path the transport uses, without spawning a process.

Run it with `atima mcp` (or `atima-mcp`) and point the client at it; tools are listed below in
`TOOLS`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import pattern

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "atima-fl-pattern"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "list_runs",
        "description": (
            "List experiment directories under a path, with attack, status, rounds and the presence "
            "of a validation history. Use this first to find the runs to analyse."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to scan (recursively, capped)"},
                "limit": {"type": "integer", "description": "Maximum runs to return", "default": 200},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_summary",
        "description": "Manifest highlights and the last written round of a single run directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"run": {"type": "string"}},
            "required": ["run"],
        },
    },
    {
        "name": "pattern_report",
        "description": (
            "Per-class metrics, damage shape and temporal structure of one run, read from its "
            "validation_history.json. Pass `clean` to also get the paired comparison."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run": {"type": "string"},
                "clean": {"type": "string", "description": "Optional clean run to pair against"},
                "window_start": {"type": "integer", "default": 41},
                "window_end": {"type": "integer", "default": 50},
                "attack_start": {"type": "integer", "default": 10},
            },
            "required": ["run"],
        },
    },
    {
        "name": "paired_verdict",
        "description": (
            "Window verdict of an attack against its clean: macro-F1 delta, per-class recall loss, "
            "benign flow and structure (episodic versus sustained)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "clean": {"type": "string"},
                "attacked": {"type": "string"},
                "window_start": {"type": "integer", "default": 41},
                "window_end": {"type": "integer", "default": 50},
            },
            "required": ["clean", "attacked"],
        },
    },
    {
        "name": "noise_thresholds",
        "description": (
            "Measure the noise of a window comparison on clean runs: spread of window means between "
            "runs, jitter inside a window, and the smallest detectable difference."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "clean_runs": {"type": "array", "items": {"type": "string"}},
                "window_start": {"type": "integer", "default": 41},
                "window_end": {"type": "integer", "default": 50},
            },
            "required": ["clean_runs"],
        },
    },
    {
        "name": "detect_latency",
        "description": (
            "First round in which each signal leaves the round-matched clean baseline, using a "
            "rolling window against the clean runs. `confirm` sets how many consecutive rounds must "
            "stay above the threshold."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run": {"type": "string"},
                "clean_runs": {"type": "array", "items": {"type": "string"}},
                "window": {"type": "integer", "default": 10},
                "confirm": {"type": "integer", "default": 2},
                "attack_start": {"type": "integer", "default": 10},
            },
            "required": ["run", "clean_runs"],
        },
    },
]


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _payload(value):
    """MCP tool results are content blocks; JSON is the least lossy choice for numbers."""
    return {"content": [{"type": "text", "text": json.dumps(value, indent=2, default=str)}]}


def _list_runs(arguments):
    root = Path(arguments["path"])
    limit = int(arguments.get("limit", 200))
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a directory")
    found = []
    for manifest in sorted(root.rglob("manifest.json")):
        run = manifest.parent
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        config = data.get("config") or {}
        found.append(
            {
                "run": str(run),
                "name": data.get("name") or run.name,
                "attack": config.get("attack"),
                "status": data.get("status"),
                "seed": config.get("seed"),
                "rounds": data.get("last_valid_round"),
                "has_history": (run / "validation_history.json").is_file(),
                "has_final_metrics": (run / "final_metrics.json").is_file(),
            }
        )
        if len(found) >= limit:
            break
    return {"path": str(root), "count": len(found), "runs": found}


def _run_summary(arguments):
    run = Path(arguments["run"])
    data = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    out = {
        "run": str(run),
        "name": data.get("name"),
        "status": data.get("status"),
        "attack": (data.get("config") or {}).get("attack"),
        "seed": (data.get("config") or {}).get("seed"),
        "rounds": data.get("last_valid_round"),
        "files": sorted(p.name for p in run.iterdir() if p.is_file()),
    }
    if (run / "final_metrics.json").is_file():
        final = json.loads((run / "final_metrics.json").read_text(encoding="utf-8"))
        federated = final.get("federated") or {}
        out["final_macro_f1"] = (final.get("test") or {}).get("macro_f1")
        out["federated_rounds"] = len(federated.get("rounds") or [])
    return out


def _kwargs(arguments, prefix):
    """Translate `window_start` / `window_end` into the positional arguments of `pattern`."""
    return {
        "start": int(arguments.get(f"{prefix}start", 41)),
        "end": int(arguments.get(f"{prefix}end", 50)),
    }


def _pattern_report(arguments):
    span = _kwargs(arguments, "window_")
    return pattern.report(
        arguments["run"],
        arguments.get("clean"),
        span["start"],
        span["end"],
        int(arguments.get("attack_start", 10)),
    )


def _paired_verdict(arguments):
    span = _kwargs(arguments, "window_")
    return pattern.paired_verdict(
        pattern.load_history(arguments["clean"]),
        pattern.load_history(arguments["attacked"]),
        span["start"],
        span["end"],
    )


def _noise_thresholds(arguments):
    span = _kwargs(arguments, "window_")
    histories = [pattern.load_history(path) for path in arguments["clean_runs"]]
    return pattern.noise(histories, span["start"], span["end"])


def _detect_latency(arguments):
    history = pattern.load_history(arguments["run"])
    clean = [pattern.load_history(path) for path in arguments["clean_runs"]]
    return pattern.detect(
        history,
        clean,
        int(arguments.get("window", 10)),
        3.0,
        int(arguments.get("confirm", 2)),
        int(arguments.get("attack_start", 10)),
    )


HANDLERS = {
    "list_runs": _list_runs,
    "run_summary": _run_summary,
    "pattern_report": _pattern_report,
    "paired_verdict": _paired_verdict,
    "noise_thresholds": _noise_thresholds,
    "detect_latency": _detect_latency,
}


def handle(request):
    """Decode one JSON-RPC request; returns the response dict, or None for notifications."""
    if not isinstance(request, dict):
        return _error(None, -32600, "Invalid request")
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    if request_id is None and method not in (None,):
        return None  # notification: nothing to answer
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {"tools": {"listChanged": False}},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            return _error(request_id, -32602, f"Unknown tool: {name}")
        try:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _payload(handler(params.get("arguments") or {})),
            }
        except Exception as error:  # reported to the client, not swallowed
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}],
                    "isError": True,
                },
            }
    if method is None:
        return _error(request_id, -32600, "Missing method")
    return _error(request_id, -32601, f"Unknown method: {method}")


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as error:
            response = _error(None, -32700, f"Parse error: {error}")
        else:
            response = handle(request)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main():  # pragma: no cover - trivial transport wrapper
    serve()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
