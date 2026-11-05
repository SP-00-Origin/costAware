# Decisions

Everything the team has decided, in order. Details and reasons are in the plan (`Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md`) and in `PHASES_1-4.md`.

## Design (September 2026)

- Research question: can an LLM agent decide when to verify its own actions using cheap risk signals, staying close to verify-everything reliability at a fraction of the cost?
- This is a research testbed, not a procurement product. Complexity is only added where it creates real verification decisions.
- Environment: a custom, deterministic "Synthetic Enterprise Procurement & Operations" simulator. It replaced the earlier e-commerce environment. τ-bench is an optional, late track.
- Orchestration: LangGraph, but every research step (policy, fault, verifier, recovery, oracle, logging) stays a separate, logged node.
- Two views of the world: the true state (only the environment and the oracle see it) and the observations the agent sees, which faults may corrupt.
- The oracle is never an LLM. It compares the true final state with the expected state and returns PASS/FAIL plus a diff.
- Faults are seeded, and the same task and seed are used across policies. Default fault rate 0.25.
- Policies: A never verifies, B verifies every step, C verifies every N steps, D verifies on high-risk actions, schema/sanity failures or low confidence.
- Recovery: re-call the same tool once; if still suspicious, re-plan with the concern; if still unresolved, log an unrecovered fault and don't force success.
- About 20 tasks are written by hand first. Only after they are validated are more generated.
- Nobody is permanently assigned to one part. All members should understand the whole pipeline.

## Phases 1–4 (October 2026)

- The simulator enforces the workflow (unknown IDs, illegal state changes, release above the approval limit without approval). It does not block policy mistakes such as ordering from a suspended vendor or going over budget. Those go through, and the oracle fails them. Otherwise a fault could never lead to a failure, and the policies could never differ.
- Orders are priced from quotes, so the agent can't invent a price.
- IDs are sequential (`PO-0001`, `APR-0001`), not random, so reruns are identical.
- 17 tools, one more than the plan: `dispute_invoice`, so invoice-mismatch tasks can be resolved.
- Tasks are written in `tasks/build_tasks.py`; `tasks/tasks.jsonl` is generated from it.
- Each tool call's fault comes from a hash of seed, tool, arguments and occurrence, so the same agent action gets the same fault under every policy.
- A timeout on a write tool still performs the write, so retries can create duplicates. This is on purpose: verification should catch it.
- The agent makes one tool call per turn and ends with a `finish` tool. Default step limit 30.
- Tests use the `scripted` provider, which replays the reference solution, so they need no API key.

## Tooling (November 2026)

- 2026-11-05: Groq added as an agent provider (`--provider groq`, default `llama-3.3-70b-versatile`). Reason: Groq is the only API key available to Krish for running the real agent.
- 2026-11-05: Repo rules, `PROGRESS.md` and this file added, following the layout of the SE project. Work continues phase by phase in the existing code; no separate prototype folders, because each phase builds directly on the code of the one before.

## Direction (November 2026)

- 2026-11-05: Follow the original plan (`Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md`) for Phases 5–13, including Policy D as the proposed method. The novelty check (`report/FUTURE_PHASES_NOVELTY.md`, 14 October 2026) is not followed for now. Reason (Krish): "Let's just go towards the original plan. If we want to change the plan later, we can. We may not follow the novelty check." Pending team review.
- 2026-11-05: Before a new phase starts, the AI tests the person starting it on the previous phase (`repo_instructions.md` §3a). If someone else did the previous phase, the test can't be skipped; if the same person did it, they may skip it. The AI explains and re-tests until they get it, instead of sending them to read files. Reason (Krish): the next phase may be done by a different person, and they must understand the work before building on it. Pending team review.
