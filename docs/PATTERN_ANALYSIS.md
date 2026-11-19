# Pattern analysis and the read-only MCP server

Two additions for the campaign on recognising poisoning patterns during federated training. Both
read artifacts a run already wrote (`validation_history.json`, `manifest.json`,
`final_metrics.json`): neither trains, and neither writes into a run directory.

## Why not `analyze`

`atima analyze` compares a verified clean/attack pair and needs `trajectory.h5`. That is the right
tool for the aggregate effect. The questions below need per-class series, temporal structure and a
measured noise floor, and they must work on runs that are not a verified pair — including partial
runs and exported histories.

## Commands

```bash
# per-class signals, damage shape and temporal structure of one run
atima pattern --run runs/E_lcg --clean runs/D_clean --window 41:50 --output pattern.json

# noise of a window comparison, measured on clean runs only
atima thresholds --clean runs/A_seed0 runs/A_seed1 runs/A_seed2 --window 41:50

# detection latency of each signal against the clean runs
atima detect --run runs/E_lcg --clean runs/A_seed0 runs/A_seed1 runs/A_seed2 --confirm 2
```

`pattern` accepts a run directory or a `validation_history.json` directly, so exported histories can
be analysed without reconstructing a run folder.

### What each number means

| field | meaning |
|---|---|
| `gate` | the stored `macro_f1` and per-class recalls recomputed from the confusion matrix; a mismatch raises instead of returning numbers |
| `window` | mean over the chosen window: the statistic a paired verdict should use |
| `structure.saturated_rounds` | rounds where at least 90% of intrusions are predicted benign (the "benign sink") |
| `structure.benign_to_rounds` | rounds where at least 1% of benign traffic goes to an attack class |
| `structure.modes` | classes that ever absorb at least 20% of the benign row |
| `structure.cv_benign_to_dos` | relative spread of that flow across rounds: high means episodic, low means sustained |
| `noise.across_runs` | spread of window means between runs: the denominator a threshold should use |
| `noise.within_window` | round-to-round jitter inside one window |
| `noise.k_min_effect` | smallest difference visible against a known reference (2.8 σ, 5% two-sided, 80% power) |
| `detect.*.first_round` | first round where the rolling mean stays `confirm` rounds above 3 σ of the round-matched clean baseline |

Conventions: rows of the confusion matrix are the true class, columns the predicted class; the
`gate` checks recall as well as macro-F1, because a flipped convention leaves macro-F1 plausible.

## MCP server

`atima mcp` (or the `atima-mcp` script) speaks JSON-RPC 2.0 over stdio and exposes six read-only
tools: `list_runs`, `run_summary`, `pattern_report`, `paired_verdict`, `noise_thresholds`,
`detect_latency`. Point a client at it, for example:

```json
{
  "mcpServers": {
    "atima": {
      "command": "atima",
      "args": ["mcp"],
      "env": { "PYTHONPATH": "/abs/path/to/ATIMA-FL/src" }
    }
  }
}
```

Every tool takes absolute paths and returns JSON as a text block; a failing tool returns
`isError: true` with the exception text instead of an empty result. The transport is stdlib only, so
adding it costs no new pinned dependency.

`list_runs` is the intended entry point: it walks a campaign directory, reports attack, status,
rounds and which artifacts exist, and lets an agent choose the runs to analyse.
