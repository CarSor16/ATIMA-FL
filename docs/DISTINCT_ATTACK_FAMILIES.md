# Additional distinct threat mechanisms (FedAvg research benchmarks)

The five new plugin IDs extend — **never replace** — the existing attack catalog.

| Plugin | Primary security mechanism | Evidence & interpretation | Relevant defenses to investigate |
|---|---|---|---|
| `class_withholding` | Data availability / training distribution manipulation | Withheld class and count; degradation in per-class recall | Trusted stratified coverage and data-quality audit; robust aggregation alone cannot restore absent classes |
| `clean_label_trigger` | Clean-label feature-space backdoor | Triggered target ASR versus clean target rate | Trusted holdout and semantic trigger testing; clipping and robust aggregation are not guaranteed cures |
| `free_rider` | Contribution integrity / zero submitted update | Zero trainable delta despite locally trained baseline | Contribution validation, suspicious zero-update audits, authenticated participation |
| `stale_replay` | Freshness of model contributions | Prior round and snapshot identity; stale-model behavior | Round-bound signed update commitments and freshness checks |
| `sybil_collusion` | Correlated logical-client influence | Shared update and participating client IDs | Client admission, authenticated identity, similarity-history detection, concentration limits |

These are **laboratory benchmark implementations**, not faithful reproductions of five claimed novel algorithms. For example, `sybil_collusion` simulates existing compromised logical IDs; it does not generate identities. `stale_replay` reads a previous local snapshot from the same run, not a packet capture. Both are model-update manipulations but have different trust assumptions and defenses. The two data-poisoning mechanisms do not collapse to random-label flipping or simple update scaling.

## Protocol and research limitations

Use `aggregation="fedavg"` for first experiments. Run a clean baseline first and supply an explicit `paired_clean` path. Match dataset hashes, seed, code/runtime and pre-attack trajectory. Keep data projections `binary` and `prepared_5` separate. Inspect per-class recall, Macro-F1, minority support, attack-active metadata, norm trajectories, and full paired analysis. Do not claim physical network feasibility for numerical triggers. Repeated matched seeds are required to estimate uncertainty; 1 seed is diagnostic.

The existing defenses (`norm_clipping`, `adaptive_clipping`, `coordinate_winsorization`, plus robust aggregators) can be tested where relevant, but FedAvg is the fixed baseline. No existing defense guarantees prevention of omission, replay or Sybil participation. Document controls required outside the aggregation stage separately.

References:
- Lin et al., *Free-riders in Federated Learning: Attacks and Defenses*, https://arxiv.org/abs/1911.12560.
- Fung et al., *Mitigating Sybils in Federated Learning Poisoning*, https://arxiv.org/abs/1808.04866.
- Bhagoji et al., *Analyzing Federated Learning through an Adversarial Lens*, https://proceedings.mlr.press/v97/bhagoji19a.html.
- Xie et al., *Model Poisoning Attacks to Federated Learning via Multi-Round Consistency*, CVPR 2025: a distinct published algorithm not implemented here, https://openaccess.thecvf.com/content/CVPR2025/html/Xie_Model_Poisoning_Attacks_to_Federated_Learning_via_Multi-Round_Consistency_CVPR_2025_paper.html.
