# Defenses and controlled comparisons

The server applies selected preprocessing stages **in their configured order**, then
one aggregation rule. In a hierarchical topology, this pipeline runs separately
in each client group. The coordinator combines group deltas using original sample
mass. These defenses receive submitted updates, not malicious-client identities.
They neither remove clients nor alter the original sample-count weights.

## Available protections

| Component | Mechanism | Candidate use | Principal limitation |
|---|---|---|---|
| L2 clipping | Fixed maximum delta norm | Update scaling, large model replacement | Direction-only or low-norm poisoning survives |
| Adaptive L2 clipping | Current-group quantile of norms | Varying update magnitudes | Corrupted clients influence the threshold |
| Coordinate median/MAD bounding | Median ± scale × max(MAD, floor) | Coordinate outliers | Honest non-IID variation may be suppressed |
| Median | Coordinatewise median | Byzantine updates | Requires a useful honest majority per group |
| Trimmed mean | Discards coordinate extremes before averaging | Coordinate outliers | Declared trim/bound must fit each group |
| Krum / Multi-Krum | Distance-based whole-update selection | Byzantine updates | Requires n ≥ 2f+3 locally; adaptive attacks can evade selection |
| Smoothed geometric median | Iterated weighted Weiszfeld on deltas | Vector outliers | Honest weight mass, heterogeneity and finite iterations matter |

Adaptive clipping and median/MAD bounding are explicit generic experimental
variants, not reproductions of a particular named defense. The geometric-median
implementation adapts the smoothed numerical oracle from [Pillutla et al.](https://arxiv.org/abs/1912.13445)
to deltas. It starts at the weighted mean and stops at the declared tolerance or
iteration budget. It **does not implement the paper's secure aggregation protocol**.
Uniform client weights are the default; sample weights are selectable and change
the corruption assumption from client fraction to weight mass.

Fixed clipping is a candidate supported by experiments in
[Sun et al.](https://arxiv.org/abs/1911.07963), not an EdgeIIoT guarantee. Median and
trimmed mean draw on [Yin et al.](https://proceedings.mlr.press/v80/yin18a.html).
Krum follows [Blanchard et al.](https://proceedings.neurips.cc/paper/2017/hash/f4b9ec30ad9f68f89b29639786cb62ef-Abstract.html).
The cited assumptions do not automatically extend to multi-epoch, heterogeneous
EdgeIIoT groups. No differential-privacy guarantee is claimed.

## Suggestions in the designer

Attack files declare threat tags; defense/aggregation files declare mitigation
tags, limitations and references. The designer matches this metadata dynamically.
Adding a plugin does not require editing a central attack/defense ID table.
Suggestions are hypotheses to evaluate, not rankings or guaranteed cures. ALIE
and adaptive Fang explicitly warn about evading robust aggregation. Update
defenses do not repair poisoned labels/features; always inspect per-class recall.

Simple mode exposes defense selection and order. Advanced exposes stage parameters.
Multiple preprocessing stages can accompany one robust aggregation rule. Order
matters and is saved/audited. For an interpretable ablation, test individual stages
before interpreting a composition.

## Four matched conditions

The GUI's **Export defense comparison study** or the equivalent CLI exports:

1. Clean + FedAvg, no defense stages.
2. Attack + FedAvg, no defense stages.
3. Clean + selected pipeline/aggregation.
4. Attack + selected pipeline/aggregation.

```bash
atima defense-study --config protected_attack.toml --workspace workspace
```

The export does not launch jobs. It declares a common round cap (at most 50) and
sets minimum stopping rounds to that cap, so clean trajectories cannot stop at
different earlier rounds. This override is recorded in `study.json`. Ordinary
single-pair experiments retain the configured plateau/recall stopping policy.
All four share data, seed, initialization, topology, training budget and attack
settings. Complete each clean before its paired attack. Use an isolated immutable
code version throughout the study; do not edit code during training.

```bash
atima analyze --clean runs/CleanUnprotected --attack runs/AttackUnprotected --output analysis/unprotected
atima analyze --clean runs/CleanProtected --attack runs/AttackProtected --output analysis/protected
atima compare-defenses --unprotected analysis/unprotected/comparison.json --protected analysis/protected/comparison.json --output analysis/defense
```

Actual run names are listed in the exported `study.json`. Analysis rejects changed
seed, horizon, data hashes, initial weights, runtime, attack source or non-defense
protocol. Source hashes for both protection and unprotected reference are retained
to prevent pooling different implementations across seeds. Older comparison JSON
without the new protocol fields must be regenerated from its original run data.

Outputs include validation trajectories, test macro-F1 recovery under attack,
clean utility change, damage reduction adjusted for clean utility, per-class recall
changes and AUD reduction. Positive recovery alone is insufficient: inspect clean
utility and class recall too. Backdoor comparisons include attacked-model ASR
reduction and the change in its untriggered target rate, requiring the same target
and eligible sample count. These are not excess-ASR estimates against a passively
triggered clean checkpoint; that additional baseline is not computed here.

For uncertainty, repeat the complete quartet with at least three independent seeds:

```bash
atima defense-statistics --inputs seed1/defense_comparison.json seed2/defense_comparison.json seed3/defense_comparison.json --output analysis/statistics
```

This produces exploratory 95% percentile bootstrap intervals (10,000 resamples).
Three seeds offer limited precision; no multiplicity correction is applied.
Rounds and clients are not independent replicates. Failed/numerically invalid
runs cannot support efficacy conclusions. Synthetic software fixtures establish
implementation behavior, not improved accuracy or defense efficacy on EdgeIIoT.
