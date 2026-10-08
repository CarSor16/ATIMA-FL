## Read-only cluster dataset catalog

The Designer now distinguishes Edge-IIoT tasks by their real class counts:

- \`Edge-IIoT · 2 classes · Binary\` (\`task=binary\`)
- \`Edge-IIoT · 5 classes · Prepared macro-classes\` (\`task=prepared_5\`)
- \`Edge-IIoT · 6 classes · Attack families\` (\`task=family_6\`)
- \`Edge-IIoT · 15 classes · Detailed attacks\` (\`task=fine_15\`)

These are **different label projections of the Edge-IIoT plugin**. The
15- and 6-class options require the corresponding source labels; they are not
proven usable merely because the taxonomy is shown. The note "source labels
required for 2/6/15" was removed from the parameter label, *not* from the
training-side label verification or safety checks.

The former research project also names four **NF-V2 raw datasets**:
NF-CSE-CIC-IDS2018-v2, NF-UNSW-NB15-v2, NF-BoT-IoT-v2 and NF-ToN-IoT-v2.
Their CSV \`Label\` and \`Attack\` columns identify binary targets and
source macro attack labels respectively. These are **shown as disabled
reference choices** in the selector (binary and macro-class), because ATIMA
does not yet include independently validated NF-V2 preparation, partitions,
feature mappings or a runnable NF-V2 dataset plugin. Do not pretend an
unimplemented NF-V2 selection can produce runnable training plans.

### Remote metadata lookup

From **Designer → Dataset labels & classification → Read dataset labels from
cluster**, ATIMA runs a read-only Python script through the existing verified
SSH connection (stored Windows credentials or preconfigured keys). It never
trains or copies source CSV, Parquet, features, shards or weights to the PC.
The request requires the local UI session token and takes no browser-supplied
paths. Reads occur **only when the user presses the button**.

By default the root for \`edge_iiot\` is taken from
\`deployment_defaults.json\` → \`dataset_root\`. The script checks required
prepared files, reads the prepared label mapping and attempts to inspect
\`fine_label\` on the train, validation and test Parquet splits. If pandas
and a Parquet engine are unavailable to remote \`python3\`, ATIMA reports
the fine-label verification as unavailable instead of claiming success.
When source labels are read, availability of the binary, family and fine
tasks is recomputed from observed labels; unavailable tasks are flagged.

The optional untracked **local workspace** file
\`cluster_dataset_paths.json\` lets you supply *already verified* raw NF-V2
CSV paths. It may contain only these keys:

\`\`\`json
{
  "nf_cicids2018": "/actual/cluster/path/NF-CSE-CIC-IDS2018-v2.csv.gz",
  "nf_unsw_nb15": "/actual/cluster/path/NF-UNSW-NB15-v2.csv.gz",
  "nf_botiot": "/actual/cluster/path/NF-BoT-IoT-v2.csv.gz",
  "nf_toniot": "/actual/cluster/path/NF-ToN-IoT-v2.csv.gz"
}
\`\`\`

The paths above are placeholders, **not verified cluster locations**. The
reader examines the \`Attack\` and \`Label\` column headings and up to the
first 20,000 records of each configured NF-V2 CSV, returning just observed
macro labels and counts. These samples are **not an exhaustive class audit**
and the four datasets remain unexecutable without their own plugins.
No directories outside the declared roots are scanned.
