# Parameter Sweep Designer and Sensitivity Explorer

## Designer

Enable an attack and configure the reference experiment normally. In the optional
Parameter Sweep Designer, read the current parameters, select one variable, enter
two to twelve distinct comma-separated levels, and reuse the multi-seed list.
The server validates every generated configuration before creating a campaign
directory. The maximum campaign size is 300 profiles.

Supported axes are numeric parameters declared by the selected attack or
partition plugin, attack start/end round, malicious client count (canonical
IDs 0 through n-1), model and partition. Changing a component selects its
default parameters unless it is the currently selected component. Review
those parameters before training. Task changes and controlled target-class
coverage require further dataset-aware implementation.

For attack-only changes, one clean reference per seed precedes all attack levels.
Model and partition changes require a separate clean per level and seed.
The ZIP contains the existing portable launchers and campaign.json, including
the axis, levels, ordered profile paths and seed list. The existing batch
runner executes sequentially only when explicitly invoked. No job is submitted
by Studio. Partition sweeps select existing audited shards, never generate them.

For example, three levels and eleven seeds yield 11 clean and 33 attacked
profiles for an attack-only sweep. A model or partition sweep instead yields
33 clean and 33 attacked profiles. Do not treat parameter magnitude as a
universal measure of attack strength.

## Results

Open Multi-seed analysis, then Parameter Sensitivity Explorer. The local API
derives sensitivity family keys from audited manifests. The key retains the
remaining recorded conditions, dataset identity, software/runtime provenance
and completed horizon. Attack-only changes require identical audited shards.
Model and partition contrasts are explicitly descriptive; partition contrasts
may vary shard and assignment hashes but require identical global data hashes.
Ambiguous multiple cohorts at the same level are excluded rather than pooled.

The table reports observed means, available pairs, and paired clean/attack
means and differences for the intersection of matched seeds across all levels.
If this intersection is empty, only descriptive observed means are available.
The figure uses equally spaced level indices (not a continuous numerical
axis), so consult the table for actual level values. Global metrics, class
recall and intrusion-to-benign rates can be selected. A single seed is an
observation, not a replicated estimate. Use the trajectory-based Runtime CLI
for stronger verification of paired inference.

Existing single-run and ordinary batch exports remain available. No web
hosting or cross-study upload is introduced by this feature.
