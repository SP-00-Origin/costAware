# Progress

What is done, what is next, and what to know before starting. Updated after each step.

## Done

| Phase | What | Where to look |
|---|---|---|
| 0 | Design frozen: environment, tools, faults, oracle, policies, metrics | `docs/Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md` |
| 1 | Deterministic procurement simulator, 17 tools with risk tiers | `src/environment/` |
| 2 | 20 hand-written tasks (7 easy, 8 medium, 5 hard) and a non-LLM oracle | `tasks/`, `src/evaluation/` |
| 3 | Fault injector (8 fault types, seeded) and replay | `src/faults/` |
| 4 | LangGraph agent, `run_agent.py`, one JSONL log per episode | `src/agent/` |

- 2026-11-05: Groq provider added, so the real agent can run with a Groq key.
- 2026-11-05: Repo rules and this file added.
- Tests: 174 pass with `python -m pytest tests -q`, no API key needed.
- Details and decisions for Phases 1–4: `docs/PHASES_1-4.md` and `docs/decisions.md`.

## Not shown yet

- Phase 4's "agent completes a meaningful subset of clean tasks" with a real LLM. This can now be done with Groq:
  `python run_agent.py --task all --provider groq`

## Next: Phase 5 — verifier and recovery

From the plan (§10, Phase 5):

- Build: a self-verifier node, a recovery node, their logs, and a demo.
- Visible progress: injected fault → verify → suspicious → recover → oracle PASS can be shown.
- Exit criterion: recovery behaves the same under every policy.
- Where it plugs in: `policy_router` in `src/agent/graph.py` already records `verify_decision`, and the step record already has `verifier_verdict` and `recovery_attempts`.
- Branch: `krish/phase5-verifier`, started from the latest `main`.

## Phases after that

6 policies A–D · 7 logging + harness · 8 first real experiment · 9 scale the environment · 10 ablations · 11–12 τ-bench (optional) · 13 analysis and paper.
