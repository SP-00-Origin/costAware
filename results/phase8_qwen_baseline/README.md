# costAware Qwen baseline

The final matched replication ran 20 synthetic procurement tasks under policies A–D
with fault seeds 7, 12 and 23, for 240 episodes. Both model roles used local Qwen3 8B.

| Policy | Initial passes / 60 | Final passes / 60 | Final verifier calls |
| --- | ---: | ---: | ---: |
| A | 32 | 33 | 0 |
| B | 36 | 37 | 642 |
| C | 36 | 36 | 241 |
| D | 37 | 38 | 322 |

D used 49.8% fewer verifier calls than B. Its paired success difference was
1.7 percentage points with a task-cluster 95% interval from 0 to 5 points.
Reliability equivalence requires a declared tolerance and further evaluation.
The replication had no runtime errors, verifier errors or agent context warnings.
All 2,464 executed tool events replayed and recomputed oracle decisions, policy
routing and workload counters matched the log.

The initial collection is d57331709a6f43088a2b58faf01093ab. The replication is
fbe4b0bd3309497da33ee617c1fe2983. Of 240 terminal outcomes, 235 agreed.
Both collections are retained. They reuse the same 20 tasks and fault seeds.

## Reading the results

Open [the research report](../../docs/costAware_Research_Report.docx) for the
methods, literature and interpretation. Download [the dashboard](dashboard.html)
and open it in a browser to inspect each scenario. GitHub displays HTML source
in its file viewer. [The short report](phase8_report.md) and
[the summary](summary.json) provide aggregate results.

## Frozen evidence

[frozen_baseline.zip](frozen_baseline.zip) contains 27 artifacts including both
collections' raw JSONL logs, source archives, freeze manifests, audits, episode
reviews, the replication comparison and the finalized editable report.
The archive's release_manifest.json supplies SHA-256 hashes.
[SHA256.json](SHA256.json) supplies hashes for the shared result files.

Extract the archive into a local folder. Activate costaware_env and rebuild the
dashboard using experiments/run_experiment.py with --from-log followed by the
path to replication/events.jsonl. Use experiments/audit_phase8.py with the same
log path to regenerate its audit and episode reports. These commands use the
frozen generation source versions. The audit detects later source changes.
The source archive allows reconstruction in a separate checkout.

Further evaluations should receive new run identities and preserve these records.
