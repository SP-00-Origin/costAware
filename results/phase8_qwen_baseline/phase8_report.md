# Phase 8 local Qwen baseline

Run fbe4b0bd3309497da33ee617c1fe2983.
Twenty synthetic procurement tasks, policies A–D, fault seeds 7, 12 and 23. Each policy ran 60 episodes.

| Policy | Pass / 60 | Success (95% task-cluster interval) | Selected actions | Verifier calls | Tokens | Mean wall seconds |
|---|---:|---|---:|---:|---:|---:|
| A | 33/60 | 55.0% (35.0% to 75.0%) | 0 | 0 | 1,779,532 | 11.1 |
| B | 37/60 | 61.7% (41.7% to 80.0%) | 576 | 642 | 2,907,126 | 28.1 |
| C | 36/60 | 60.0% (40.0% to 80.0%) | 213 | 241 | 2,228,872 | 17.3 |
| D | 38/60 | 63.3% (43.3% to 81.7%) | 263 | 322 | 2,502,825 | 19.6 |

## Paired differences from B

Each difference uses the same task and fault seed. Intervals resample 20 whole tasks with replacement 2,000 times.

- A minus B was -6.7 percentage points (95% interval -25.0 to 10.0).
- C minus B was -1.7 percentage points (95% interval -15.0 to 13.3).
- D minus B was +1.7 percentage points (95% interval 0.0 to 5.0).

## Observed frontiers

Efficient policies maximize success at a given mean per-episode cost. A cheaper or equally costly policy with at least as much success dominates when one inequality is strict.

- calls: A, C, D on the frontier.
- tokens: A, C, D on the frontier.
- seconds: A, C, D on the frontier.

API charges were zero for these local calls. Electricity and ownership cost were unmeasured. The mean-budget envelope in audit.json is descriptive. It does not simulate imposing a hard limit during an episode.

## Audit and artifacts

Replayed 2,464 tool events. Checked all 240 planned task–seed–policy combinations, 20 reference solutions, 20 empty controls and 20 negative controls. Verified the final-state oracle, policy routing and workload counters against the log.

The dashboard plots success against verifier calls per action. The episode index records every terminal outcome. The chronological review lists every fault, selection, verdict, subsequent action and failed oracle requirement. Faults followed by failures are associations. An agent can miss a requirement despite an accurate reread or finish correctly after a corrupted receipt.

With the frozen generation sources, rebuild the audit from the repository root.

```powershell
python experiments/audit_phase8.py output/experiments/fbe4b0bd3309497da33ee617c1fe2983/events.jsonl
```
