# Progress

What is done, what is next, and what to know before starting. Updated after each step.

## Done

| Phase | What | Done by | Where to look |
|---|---|---|---|
| 0 | Design frozen: environment, tools, faults, oracle, policies, metrics | Team | `docs/Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md` |
| 1 | Deterministic procurement simulator, 17 tools with risk tiers | Krish | `src/environment/` |
| 2 | 20 hand-written tasks (7 easy, 8 medium, 5 hard) and a non-LLM oracle | Krish | `tasks/`, `src/evaluation/` |
| 3 | Fault injector (8 fault types, seeded) and replay | Krish | `src/faults/` |
| 4 | LangGraph agent, `run_agent.py`, one JSONL log per episode | Krish | `src/agent/` |
| 5 | Self-verifier, one-retry recovery, replanning concerns, logs and offline demo | Krish | `src/verifier/`, `src/agent/graph.py`, `scripts/demo_recovery.py` |

When a phase is finished, add its row with who did it. The AI uses "Done by" to decide whether to test the next person (`repo_instructions.md` §3a).

- 2026-11-05: Groq provider added, so the real agent can run with a Groq key. It is in its own pull request (`krish/groq-provider`); merge it before this one.
- 2026-11-05: Repo rules and this file added.
- Tests: all pass with `python -m pytest tests -q`, no API key needed.
- Details and decisions for Phases 1–4: `docs/PHASES_1-4.md` and `docs/decisions.md`.

## Not shown yet

- Phase 4's "agent completes a meaningful subset of clean tasks" with a real LLM. This can be done with Groq once `krish/groq-provider` is merged:
  `python run_agent.py --task all --provider groq`

## Phase 5 validation — 2026-11-18

- Implemented on `krish/phase5-verifier`, based on `krish/repo-structure` plus
  existing Groq support (`070eda1`). Phase 5 changes are not committed yet.
- Verifier receives only the goal, action and observed history, never true results,
  fault labels or oracle metadata. Real providers use a separate model instance.
- A suspicious result gets one same-tool retry through the normal fault injector,
  then another check. Continued suspicion goes to the agent for replanning.
  Verifier failures request replanning without repeating a potentially successful write.
- Same recovery rules under B/C/D; A skips verification and recovery. C retains its
  existing zero-based schedule (agent steps 0, 3, 6), unaffected by extra retry calls.
- Logs include both tool attempts, verdicts/errors, final result used, calls, tokens,
  verifier latency and unresolved concerns. `recovered_steps` means the verifier
  accepted a retry, not that the true state is correct; only the oracle establishes success.
  `unrecovered_steps` counts concerns unresolved at the automatic retry limit.
- Validation: `venv\Scripts\python.exe -m pytest tests -q` — 221 passed.
  Includes all 20 clean tasks under A–D, bounded retries, timeout-after-write duplicates,
  observed-only verifier input, replay and error accounting.
- Demo: `python scripts/demo_recovery.py` — same initial wrong budget, A fails,
  B detects the conflict, retries, changes supplier and passes. Logs: `logs/phase5_demo/`.
- All validation is offline. Scripted verifiers are test stand-ins, not LLM reliability
  results. Live Groq/Anthropic verification has not been run in this step.
- Follow-up review (2026-11-18): verifier, recovery, graph integration, provider wiring
  and related tests inspected; no blocking issue found in that scope. Full suite rerun:
  221 passed. Git branch/history and remote freshness were not checked in this review.
- CLI: `python run_agent.py --task T01 --provider scripted --policy B`.
  Real runs use the selected provider and agent model by default; `--verifier-model`
  overrides the verifier model. Programmatic B/C/D runs must supply `verifier_llm`.

## Next

User Git review and commit of Phase 5 are next. Then plan Phase 6 (policy
configuration and comparisons) on a user-selected branch. Continue following the
original plan, not the novelty proposal; see `docs/decisions.md`.

## Phases after that

6 policies A–D · 7 logging + harness · 8 first real experiment · 9 scale the environment · 10 ablations · 11–12 τ-bench (optional) · 13 analysis and paper.
