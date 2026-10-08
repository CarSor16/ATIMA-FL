# Ten attack mechanisms

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
