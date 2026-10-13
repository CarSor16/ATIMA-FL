# Universal tabular datasets — initial supported workflow

The runtime is independent from a cluster. These commands operate on the **local filesystem of the machine where they are run**, whether it is a laptop or a separately configured cluster. An SSH connection is not required. CSV, CSV.GZ and Parquet are supported; a directory includes up to 64 direct-child supported files with **identical** column layouts (no recursion).

## Inspect first — never guess label semantics

\`\`\`bash
atima datasets inspect /path/to/raw.csv
\`\`\`

The result suggests label columns by name or cardinality. The user **must** choose \`--label-column\` and (for a binary task) \`--benign-label\`. Heuristic guesses are not treated as confirmed ground truth. High-cardinality strings must be explicitly excluded; obvious ID, timestamp, source/target labels are excluded automatically. Additional exclusions are explicit.

## Prepare once

\`\`\`bash
atima datasets prepare /path/to/raw.csv --output /path/to/prepared-v1 \
  --label-column Attack --benign-label Benign --clients 10 --seed 2026 \
  --exclude source_ip --exclude destination_ip
\`\`\`

The output is *not* written over its inputs or an existing prepared tree. Every class must have at least three unique feature groups, enough train samples for all clients, and valid numeric/categorical features. Splits are stratified by class and feature group; transforms use training data only. The tool produces parquet splits, separate persisted IID/Dirichlet α=0.5 client shards, assignment tables, stable source-row IDs, class mapping, numeric/categorical preprocessing, source hashes and an immutable audit manifest. Class/count dimensions are discovered from its response.

Current in-memory import is bounded to **500,000 rows by default**; larger data require explicit \`--max-rows\` and adequate RAM. This is a limit of the first implementation, *not* a claim to support arbitrary terabyte-sized sources.

## Training configuration

Set \`dataset = "universal_tabular"\`, \`dataset_root\` to the prepared directory, \`dataset_params.task = "multiclass"\` or \`"binary"\`, and **copy \`input_dim\`/\`num_classes\` from the preparation response**. Existing \`iid\` and \`dirichlet\` partitions are supported because the preparer persists the expected shard structures.

All historical Edge-IIoT adapters and attack plugins remain intact. The paired-run preflight checks data hashes, class mapping, shard correspondence, code identity and runtime identity. No raw CSV is sent to Flower workers; workers read prepared shards through a uniform DataBatch contract.

## Scientific limitations

- Automatic semantic detection of normal/benign traffic is **not claimed**: always declare it.
- No implicit mixing of unrelated directory schemas.
- No promise of temporal/host/capture separation: feature-group disjointness is enforced, capture disjointness is reported **false**.
- Dropping source IP, timestamp or identifiers from feature vectors does not remove their information from correlated features.
- Dataset preparation should be frozen before paired baselines/attacks; changing any prepared artifact changes its hash and invalidates comparisons.
- Binary evaluation requires the benign class to be present in the source.
