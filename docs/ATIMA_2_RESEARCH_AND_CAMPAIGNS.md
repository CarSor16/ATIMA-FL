# ATIMA 2.0 — Experiment organization and research gates

Status: implementation roadmap; **not an authorization to launch experiments**.
Target development base: `studio-runtime-split`. Keep the experimental
Studio/Core/Runtime packaging separation and canonical attack taxonomy.

## Evidence baseline

- Existing archival results do **not** prove that a plugin is an effective attack.
- Historical paired clean/attack validity depends on compatible source identity,
  dataset hashes, label mapping, partition, seed, round horizon and initial state.
- A result that is better than its clean baseline is not automatically a framework
  bug; classify it as an observed positive/negative difference and investigate
  noise, convergence, target metrics and the actual poisoning trace.
- The full research question is not yet chosen. Prefer a narrow, falsifiable NIDS
  scenario over a claim that adding more attacks to a benchmark is original.

## First implementation: Results campaign explorer

Use the core's `classify_attack` for *implemented* attacks. Preserve unknown
historical IDs as unclassified, never silently add them to the runtime catalog.
The grouping is a browse/search view, not a comparison eligibility gate.

Identity and reporting dimensions:
- Attack family, canonical attack ID, campaign date **if grounded**, model,
  task, dataset, IID vs non-IID and persisted partition parameters (especially
  Dirichlet alpha).
- Seed and attack parameters must remain visible per run; do not collapse
  attack intensities into an averaged causal effect without explicit strata.
- No filesystem renames, manifest rewrites or cluster synchronization on page
  load. Unknown campaign dates remain unknown.
- Use the existing verified baseline pairing and dataset compatibility checks
  for deltas. Never infer a clean baseline from a matching folder label.

## Next stage: multi-seed planning

Define an explicit, versioned **inclusive** seed schedule `0..10` (11 seeds).
Each attacked run must point to a validated clean for the *same* seed and
persisted partition. Reuse one clean per comparable seed/split/model/task
configuration, not one clean across different data partitions or source versions.
Separate attack RNG from initialization and partition RNG where possible and
record how the streams are derived.

Campaign planning must be a dry-run by default: preview unique run IDs,
expected clean count, attack count, duplicate detection, approximate job budget,
and export-only plans. Never schedule Slurm jobs implicitly from Studio.

## Attack strength experiments

Strength is **multidimensional and attack-specific**, not an arbitrary maximum
of a single scale. Each comparison needs predeclared:
- Threat model and attacker knowledge (local vs oracle, collusion, compromised
  fraction and sample-mass fraction).
- Timing, target metric, attack parameters, numerical validity safeguards and
  realistic-feature constraints where applicable.
- Distinct exploratory sweep (validation selection) and independent test
  evaluation. No tuning to test labels/results.
- Standard / Strong / Oracle are tagged hypotheses, not certified potency
  levels. A very strong synthetic scenario can be a positive control, but not
  evidence of real-world feasibility.

## Statistical analysis and UI

Store per-seed paired deltas, class-wise confusion/recall changes, trajectory
statistics and positive attack-application evidence. Report variance, paired
confidence intervals and a practical damage threshold. Multiple metrics and
strength sweeps require explicit multiplicity/selection caveats. Never label
nonsignificance as proof of no effect.

## First follow-up implemented as a bounded preview/import milestone

Studio now offers a session-token-protected **Preview paired campaign · seeds
0–10** action. It shows 11 clean and 11 attacked run names, paths, order and
a fixed stopping horizon for the currently configured attack. The preview
validates configuration but does not check data, allocate resources, create
TOML/ZIP plans or submit jobs. Seed planning for multiple attacks and actual
batch-plan exports remain future work; the preview is not a scheduler.

`src/atima_fl/ui/cluster_results.py` now supports **explicit pagination** of
up to 100 result summaries per request. The original import button fetches
the first page; when another page is available it offers a next-page action.
Each page retains the existing bounded read-only SSH transport, JSON field
whitelist and host-key checks. Remote directory churn between page requests
can move the numeric offsets; for rigorous archives, freeze the remote
campaign while importing or use a future stable snapshot/cursor protocol.
For a four-attack × two-partition × 11-seed campaign (88 attacked runs plus
potentially 22 clean runs), at least two page requests may be required.
No implicit bulk sync or cluster jobs are started.

## Candidate narrow research gaps (not claims of novelty)

1. Target-class failures invisible to global IDS metrics, especially DoS and
   confusing related attack families.
2. Conditional attack feasibility/effectiveness when malicious clients lack
   target-class support under severe class imbalance/non-IID.
3. Small or coherent malicious update directions that are hard to distinguish
   from ordinary non-IID benign heterogeneity.

Select a final question only after mapping relevant papers and obtaining
reproducible paired, multi-seed evidence under a frozen protocol.

## Acceptance before merging this PR

1. Python regression tests for grouping; JS Results functional tests.
2. Full current-branch suite and split-package installation/CI checks.
3. Manual browser checks: nested groups, empty/legacy runs, large result sets,
   safe HTML text rendering, and existing A/B comparison.
4. Compare the output against actual historical manifests without changing them.

## Optionality contract (requested)

Every new workflow is **opt-in**. The legacy single-experiment config,
TOML/ZIP export, and normal Results comparison remain available. The Results
view starts **flat**, and the user may explicitly enable attack/campaign
grouping. The optional research focus uses the attack IDs appearing in the
user-supplied three-task graphs (`All_Attacks_By_Task.pdf`): ClassWithholding,
LocalClassGradient, ModelReplacement, SampleWeightHijack, StaleReplay,
UpdateScaling x5, PoisonedFL, FreeRider and LabelFlip to benign. These are
**nine** named attacks with plotted or partially plotted results, not seven;
ClientDropout is separately discussed as early termination rather than final
classification efficacy. No unsupported assumption is made about which seven
the researcher wants to select.

Research focus is a **presentation filter only**, disabled by default.
Users can select or deselect individual IDs; clean baselines remain visible.
It does not modify pairing rules, campaign export, attack strength, historical
manifests or experiment training. Attack ID matching alone does not establish
that an individual run uses exactly the same parameters as the PDF (for
example LabelFlip target or UpdateScaling multiplier); inspect each recorded
configuration before scientific comparisons.

The figures use one malicious client, 10 clients in total, one server,
LopezCNN, FedAvg without defenses, 30 rounds, three local epochs and exploratory
seed 2026. They contain IID/non-IID comparisons, not proven causal isolation:
some configurations/shards differ. LocalClassGradient shows severe degradation,
while ModelReplacement's reported triggered intrusion-to-benign rate differs
sharply between IID and non-IID. In the original 16-class non-IID
ModelReplacement run, the clean-with-trigger control is explicitly unverified;
none of the graphical observations alone establishes real-world attack
feasibility or multi-seed reliability.

## Working research path: isolated-client LCG across global and personalized FL

**Question under investigation:** when one isolated NIDS client applies local-only,
target-class gradient ascent, does its effect on target-class recognition differ
between standard LopezCNN FedAvg and the optional HyperFL++ personalized
hypernetwork protocol? This is a testable working question, not a novelty claim.
HyperFL++ addresses gradient-inversion privacy; it is not presented as a
poisoning defense.

### Bounded protocol

- Use one prepared Edge-IIoT task and its audited label mapping. Begin with the
  existing five-class task and non-IID Dirichlet alpha 0.5. Do not assume a
  target class index: resolve it from the dataset manifest and record the
  compromised client's target-class support first.
- Compare four conditions per seed: Standard/No Attack, Standard/LCG,
  HyperFL++/No Attack, HyperFL++/LCG. Keep 10 clients, one aggregation server,
  and exactly one malicious client. Within each training method, the attacked
  run must pair to its own same-seed, same-partition clean run.
- Fix the compute budget at 50 server rounds × 4 local epochs = 200
  client-epochs per client. HyperFL++ uses one of these four epochs for its
  private head and three for its generated features; report that distinction.
  Activate LCG in rounds 10–50. Check that paired trajectories are identical
  through round 9.
- First run one seed as a technical and feasibility pilot. Only after its
  manifests, target support, attack trace, HDF5 updates, and metrics pass should
  the paired design expand to seeds 0–10 (44 runs total before any extra IID
  stratum). The single-seed pilot is not statistical evidence.
- The local adversary may use only its own shard, private client state, and
  current global hypernetwork/model parameters. It must not read other clients'
  updates or server validation/test labels. Log the local objective, gradient
  norm, perturbation budget, submitted-update difference, and exact application
  rounds.

### Outcomes and interpretation

Primary outcome: paired change in recall for the target intrusion class.
Also report intrusion-to-benign errors, benign false-positive rate, macro-F1,
per-class confusion, and update norm/direction. For HyperFL++, report client
personalized outcomes as well as pooled confusion counts; its validation/test
path evaluates personalized client models on the prepared shared evaluation
split. Compare attack-minus-clean deltas within each method, not raw scores
alone across different model protocols.

A technically applied attack is not necessarily an effective attack. Preserve
null or beneficial outcomes. If target support is absent, classify the run as
infeasible for that client/partition rather than a successful attack. The
current CPU Flower fixture is only a software regression test; it does not
validate cluster GPU execution, full-data convergence, capture independence,
or a real deployment threat model.

The current implementation adapts LCG to HyperFL++ by ascending the target
class loss through the client-specific embedding into the shared hypernetwork
parameters. This changes the parameter space and must be described as an ATIMA
adaptation of LCG. It is not equivalent to the original direct LopezCNN-weight
perturbation; report the two methods separately.
