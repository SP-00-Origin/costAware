# Phase 7 checks and Phase 8 startup

## Scope of the Phase 7 gate

The original implementation plan's Section 10 requires a runner, config system,
JSONL logs and parser, with one-command small experiments and no manual spreadsheet
copying. Passing this gate validates the harness; it does not establish that a real
model or adaptive policy is reliable.

The expanded metrics plan includes further cost/budget analysis. Monetary billing
estimates, hard spending enforcement and full budget curves are not complete in
the current harness. Do not describe every expanded-plan requirement as finished.

## Final check performed on 2026-11-21

In `costaware_env` (Python 3.11.15):

| Check | Evidence |
|---|---|
| Full test suite | 387 passed; no API key needed |
| Task validator | 20 tasks valid; references pass and declared negatives fail |
| Config-driven experiment | 16/16 scripted episodes completed and passed the oracle |
| JSONL reconstruction | Reports rebuilt with unchanged summary values |
| Action replay | All 16 trajectories reproduced without true/observed/fault mismatches |
| Generated artifacts | Raw events, summary, paired comparison and run/project dashboards |

Final smoke run ID: `4d289b3ea7fb4bcfbd64b1354cf9d9f2`. Its generated files are local
artifacts under `output/experiments/`, not files to commit. The checks demonstrate
the original Phase 7 engineering exit criterion.

## Repeat the automated check

```powershell
conda activate costaware_env
cd D:\costAware
python -m pytest tests -q
python scripts/validate_tasks.py
python experiments/run_experiment.py --config experiments/configs/phase7_smoke.json
```

Use the new run ID printed by the runner:

```powershell
$runId = Read-Host "Paste the run ID printed by the batch runner"
python experiments/run_experiment.py --from-log "output/experiments/$runId/events.jsonl"
python experiments/dashboard_server.py
```

Open the dashboard and confirm 16 planned/finished episodes across A–D, readable
traces, distinct selected-action/verifier-call counts and the saved run configuration.
The automated suite also covers interrupted runs, provider failures, metric examples,
report reconstruction and information boundaries.

## Before starting Phase 8

1. Review the implementation and pending decisions, then commit/review the agreed
   Phase 7 state. Keep generated output and API keys out of commits.
2. Complete the repository's conversational understanding check before a new phase
   (`repo_instructions.md` §3a). It is distinct from pytest and is not recorded as
   test scores in the repository. If the same person completed the previous phase,
   the check is offered; otherwise it is required.
3. Review T18: it fails under every policy even with clean observations. Decide
   whether to improve general evidence handling or retain and report that model
   limitation. Do not silently remove difficult tasks to improve success rates.
4. Review context adequacy. Faulted T18/B reported five near-context calls at 8192.
   Select a feasible context/history strategy and validate it before freezing runs.
5. Choose one model/provider and freeze task definitions, prompts, model identity,
   context, response limits, policy settings, fault rate and seeds. Do not tune
   these during baseline collection. Preserve failed and interrupted outcomes.
6. Run a small clean/faulted preflight under matched settings, including multiple
   seeds before the full baseline. Inspect representative traces, not just totals.

These steps are preparation instructions. Creating this guide does not start the
full baseline, choose a final model or certify that the remaining limitations are fixed.

## The first research baseline

The plan calls for **one model × four policies × 20–50 tasks × 3–5 trials**. With the
current dataset, 20 tasks × four policies × three seeds gives **240 episodes**.
Seeds/trials are matched across policies. Fault matching is action-keyed, so changed
agent behavior can still encounter different faults.

The existing `phase8_gemini_baseline.json` already describes a 240-episode grid.
There is not yet a frozen local-Qwen baseline config. After the readiness review,
copy a local validation config, set `tasks` to `["all"]` and `seeds` to `[7, 12, 23]`,
retain explicit agreed model options, and save it under a new baseline filename.
For Groq, use an explicit accessible model ID and an agreed provider budget.

Run the chosen config through the existing harness:

```powershell
python experiments/run_experiment.py --config experiments/configs/<chosen_baseline>.json
```

Do not execute placeholder paths literally. Use [RUN_COMMANDS.md](RUN_COMMANDS.md)
for currently available, runnable pilot commands.

## Phase 8 deliverables and exit criterion

- A frozen run config and the exact task/model/prompt/runtime identity.
- Raw JSONL retaining all configured outcomes, including failures.
- Results table and reliability-versus-verification-workload plot.
- Matched comparisons with B and uncertainty estimates, with sample counts.
- Representative successful and failed trajectories, with interpretation.
- A short report stating what the evidence supports and its limitations.

The exit criterion is a reproducible path from config to raw logs to results and
plots, with genuine model evidence. The current five-task pilot is not that full
baseline. Do not proceed to scaling simply because the harness test passed.

## Existing local evidence

The clean and faulted five-task runs each produced 4/5 oracle passes per policy.
Clean verifier calls for A/B/C/D were 0/45/14/15; faulted calls were 0/71/19/27.
Both sets replayed exactly from recorded task snapshots, with zero provider or
verifier-format errors. These results identify workload and remaining weaknesses;
they do not prove that D is superior.

For a change summary and run IDs, see
[edits/EXPERIMENT_SETUP_CHANGES.md](edits/EXPERIMENT_SETUP_CHANGES.md).
