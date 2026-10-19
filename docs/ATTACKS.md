# Poisoning attack mechanisms and research limitations

These mechanisms overlap taxonomically. The five generic additions are
transparent benchmark controls, not novel attacks. Choose intensity and threat
assumptions before looking at results.

| Mechanism | Operation | Assumption / interpretation |
|---|---|---|
| LabelFlip | Selected source labels become a target label | Local data; targeted class confusion |
| ALIE | Estimated mean minus z times coordinate standard deviation | Local collusion or explicit oracle; 10 clients/2 colluders gives automatic z=0 |
| IPM | Opposes benign aggregate direction | Oracle; adapted to multi-epoch deltas |
| Fang | Search against trimmed mean or Krum | Full knowledge variant; transfer to another aggregator is declared |
| ModelReplacement / backdoor | Trigger data and amplify submitted delta | Counts/total sample mass; report ASR on eligible non-target examples and clean target rate |
| Random labels | Replace selected labels with a different random class | Local data; every selected label changes |
| Feature noise | Gaussian noise on selected numerical coordinates, clipped | Not a physically validated packet attack; feature/padding semantics require dataset-specific validation |
| Sign flip | Submit minus-strength times local delta | Trainable parameters; buffers protected |
| Gaussian update noise | Add isotropic Gaussian direction at relative delta L2 budget | Normalized additive variant; zero update has zero relative budget |
| Update scaling | Multiply local delta by factor >=1 | Amplification; may help or hurt, efficacy must be measured |

All attacks are client-side and respect malicious IDs and an explicit round
window. Raw and submitted updates are stored separately. Shared storage enables
declared collusion/oracles; it is not a privacy boundary.

References: [ALIE](https://proceedings.neurips.cc/paper/2019/file/ec1c59141046cd1866bbbcdfb6ae31d4-Paper.pdf),
[IPM](https://proceedings.mlr.press/v115/xie20a/xie20a.pdf),
[Fang](https://www.usenix.org/system/files/sec20-fang.pdf),
[model replacement](https://proceedings.mlr.press/v108/bagdasaryan20a.html),
[label flipping](https://arxiv.org/abs/2207.01982),
[network data poisoning](https://arxiv.org/abs/2403.02983),
[SoK benchmarking poisoning](https://arxiv.org/abs/2502.03801).

## Planned evaluation

Complete preflight and a pilot before scientific pairs. Match clean/attacked
dataset hashes, source, runtime, initial weights and pre-attack trajectory.
Measure macro/weighted F1, accuracy, balanced accuracy, MCC, loss, class recall,
global L2/cosine distances, client transform norms and positive F1-gap area.
Failed/NaN runs are numerical failures, not valid final accuracy measurements.
The test set is evaluated only after training; early stopping uses validation.

For efficacy comparisons use independent paired seeds (minimum three for the
implemented exploratory bootstrap), fixed conditions and predeclared metrics.
More seeds, intensity sweeps, non-IID alpha=0.5, alternative aggregators and
defense pipelines follow. Alpha=0.1 and multiattack groups remain deferred.
Account for multiple comparisons in a later confirmatory statistical protocol.


## Additional research mechanisms (pilot stage)

The following two **additional mechanisms** are implemented for *future*
paired cluster experiments. They have **not** been validated for scientific
attack efficacy; do not interpret plugin availability as a success claim.

### `sample_weight_hijack` — FedAvg metadata integrity

- **Threat model:** an authenticated malicious logical client may lie about
  its training-sample count. It cannot change server-side code or forge more
  client identities. Real deployments can defeat this if sample mass is
  independently verified or fixed by the server.
- **Mechanism:** the `report_count` attack hook multiplies its original,
  positive shard count by a configurable integer `count_multiplier` (2–20)
  in **both** Flower phases. The reported count is used by sample-weighted
  FedAvg. The actual local training data and submitted model are untouched.
- **Audit:** `original_samples` continues to record actual simulation shard
  size; `reported_samples`, `count_spoofed` and `actual_sample_mass` are
  metadata. The FL Results audit contrasts malicious mass before and after
  claimed-count manipulation. Client-submitted counts are *not trusted facts*.
- **Research control:** compare the *same* malicious client, seed, dataset and
  local update with truthful and manipulated sample counts. A clean/attacked
  paired run with the same scientific source/runtime is required.

### `local_class_gradient` — target-class model integrity

- **Threat model:** the malicious client sees only its own local labelled
  shard and locally trained model. It does **not** observe benign client
  updates, other client data, server validation labels or the global test set.
- **Mechanism:** after local training, take one bounded ascent step on
  cross-entropy for up to `max_examples` genuine local examples of
  `target_class`. The L2 magnitude of the injected parameter perturbation
  is `relative_budget` times the L2 norm of its *own* clean local model
  delta. Only trainable parameters are altered; CNN buffers are preserved.
- **Guard:** if the targeted class has zero local support, the plugin reports
  `attack_applied: false` with an explicit reason. It does not invent
  examples or access data outside its shard.
- **Interpretation:** this maximizes *local target-class loss*, not
  necessarily test-set attack success. It makes no stealth/other-class
  preservation guarantee; non-IID support and paired per-class recall must
  be verified experimentally.

### FL-specific evidence in Results

New runs now retain compact server-audited `final_metrics.json.federated.rounds`
containing claimed/actual malicious sample mass, active poisoned clients,
count discrepancies, client-update L2 norms and global-step L2. Results offers
a round chart with zoom and CSV export. Existing historical runs lack this
extension and remain viewable as historical classifier metrics — they are
**not** retroactively reconstructed. Only successful completed runs include
the new final-round telemetry; no private datasets or model weights are
downloaded by the optional read-only cluster summary import.

**Compatibility caution:** changing training code changes the experiment's
source identity. Existing clean HDF5 trajectories cannot be used as the paired
baseline of runs produced by the modified implementation. Complete a new
compatible clean run first. These changes do not launch cluster jobs.
