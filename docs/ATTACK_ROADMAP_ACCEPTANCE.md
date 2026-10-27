# Scientific completion gates before an ATIMA-FL merge

This is a status/acceptance document, not evidence of attack efficacy.

## Implemented on this branch

- Separate Studio/Core/Runtime wheels and dependency-only atima-full meta wheel.
- Attack category metadata with literature references on Registry.catalog().
- Min-Max and Min-Sum oracle geometric Byzantine attacks with bounded-distance tests.
- Random Byzantine reproducible untargeted baseline (random local model delta, relative L2 budget).
- Existing 17 attacks preserved. The catalog now covers 20 attack plugins plus the clean 'none' baseline.

## Verification required

1. CI: scientific Python tests, frontend on Linux/macOS/Windows, isolated Studio/full wheel build.
2. Multi-seed clean/attacked paired NIDS experiment for each Byzantine attack; same data hash, configuration, seed and training horizon.
3. FedAvg vs median, trimmed mean, Krum and Multi-Krum; record per-class recall, macro-F1, norms, aggregation audit and feasibility of the attack's knowledge assumptions.
4. Independently audit multi-server grouping and oracle knowledge boundaries. Oracle variants must never be reported as attacks achievable without oracle visibility.
5. Check source identity and result-manifest comparability before combining older and newer runs.

## Not implemented / out of merge scope for the packaging and Byzantine-baseline milestone

- Gradient-ascent *training* attack: needs an explicit malicious local optimizer/training hook, not merely a relabeled sign flip.
- Adaptive scaling and non-IID-aware attacks: require explicit observable feedback and no forbidden benign-update oracle.
- Targeted traffic-semantic attacks, NIDS inference-time evasion, and durable/distributed backdoors: require feature validity constraints and task-specific attack success metrics.
- Membership/property inference and reconstruction: need privacy-attacker observation and separate metrics.
- Malicious server and channel attacks: need server and transport threat-model hooks.
- Actual cluster Slurm/CUDA runs and merge into main.

Do not call the entire survey taxonomy implemented. Each attack should have documented capability assumptions, reproducible fixtures, deterministic seeds, validation, and paired experiments before scientific conclusions are drawn.
