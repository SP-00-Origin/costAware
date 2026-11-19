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
| 6 | Configurable A–D timing, observed-result checks, action confidence and comparison demo | Krish | `src/policies/`, `src/agent/`, `scripts/demo_policies.py` |

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
  existing Groq support (`070eda1`). Krish's post-fetch Git output on 2026-11-18
  confirms Phase 5 commit `d4eafe5` matches `sp/krish/phase5-verifier`.
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

## Phase 6 validation — 2026-11-18

- Krish confirmed the Phase 5 PR is open and approved the three-step Phase 6 plan.
- User-created branch: `krish/phase6-polices` (exact spelling), from Phase 5 `d4eafe5`.
- Step 1 implemented, not committed: `src/policies/config.py` validates interval
  and confidence threshold; defaults remain 3 and 0.6. Policy C stays zero-based.
- Policy D checks required fields and types across all 17 tool outputs, including
  nested records, finite/non-negative numbers, budget/quote arithmetic and status
  consistency. Checks use only observations; valid empty lists and declined discounts
  are accepted. Passing these checks is not proof of oracle success.
- Step 2 implemented, not committed: all A–D agent tool schemas request `_confidence`
  with the action. The graph removes it before simulator execution and fault-key creation.
- D reads validated action confidence, never confidence embedded in a tool result.
  Logs record `action_confidence` and `confidence_source` (`self_reported` or `unavailable`).
  Missing/invalid scores become null; other D triggers still apply. Automatic retries
  have no newly generated score. The scripted reference agent does not invent one.
- Prompt/tool format is identical under A–D; confidence adds no extra model call.
  This is self-reported action confidence before the result, not calibrated correctness.
- Step 3 implemented, not committed: `build_graph()` and `run_episode()` accept
  `policy_config`; validate/copy it before execution and retain the resolved settings
  plus `max_steps` in episode summaries, including failed runs.
- `scripts/demo_policies.py` runs one task under all A–D with fresh, identical scripted
  models and the same fault seed/rate/limits. CLI accepts interval and threshold.
  Default runs write to a new folder under ignored `logs/phase6_demo/`.
- Validation: `venv\Scripts\python.exe -m pytest tests -q` — 343 passed.
  Covers confidence isolation, invalid inputs, settings/log roundtrip, retry scheduling,
  seeded replay and comparison CLI behavior, alongside all existing tests.
- Demo: `venv\Scripts\python.exe scripts/demo_policies.py --task T01 --seed 7 --fault-rate 0.25`
  — exit 0. A/B/C/D selected 0/5/2/4 actions for verification, no retries; all oracle PASS.
- These are offline plumbing checks. Scripted actions do not adapt or report confidence,
  and the scripted verifier checks explicit errors only; no live reliability result.
- Core Section 10 Phase 6 implementation is complete; Git review/commit/PR remain pending.

## Phase 7 implementation on siddharth/phase7-harness

- Added a config-driven A–D experiment runner, append-only JSONL, replayable summaries, matched comparisons against B, and a local HTML dashboard with episode traces.
- The dashboard counts selected agent actions and actual verifier calls separately. Rechecks count only toward calls.
- Gemini and OpenAI are available alongside the existing providers. The verifier uses its own tool-free model instance.
- Offline validation: 348 tests passed. All 16 planned episodes completed in the scripted batch. The JSONL regenerated the summary, paired comparison, and dashboard.
- Pending review and commit. After review, run a small matched Gemini pilot before freezing the Phase 8 experiment config. The scripted batch validates the harness and supplies no live reliability or pricing evidence.

## Phase 8 Gemini preflight

- Added live pilot and baseline configs and offline fault-label diagnostics to the dashboard. The 20-task baseline validates as 240 paired episodes.
- The eight-episode pilot was interrupted while waiting for Gemini. A bounded T01 Policy A retry executed two tool actions and then ended in a recorded GoogleAPIError. Both logs are visible as incomplete or errored runs. No comparative live result is available yet.
- The runner now records safe HTTP status details and uses bounded Gemini retries. A further T01 Policy A rerun recorded HTTP 503 Service Unavailable in run `071ccddc86584528afb8278a70331cec`. The eight-episode pilot and baseline are still pending.
- Offline validation: 351 tests passed. Run the eight-episode pilot again when generation requests are stable, then use the baseline config.
- Latest Gemini pilot (`859a497b89074c8db4653c6b41dbda3f`): five oracle passes in eight planned episodes. D passed both tasks with eight verifier calls and no verifier errors. Agent-side HTTP 503/504 errors stopped both B episodes and one C episode, leaving no completed pairs against B.

## Phase 8 Groq pilot follow-up

- Groq GPT-OSS agents now use a 4,096-token response budget. Episode reports record agent finish reasons, tool-call counts and token usage. A length-limited response without a usable tool call gets one retry.
- The Groq GPT-OSS verifier requests JSON objects and validates the verdict. All verification policies send suspicious writes back to the agent with a read-only state-check instruction. Automatic recovery still retries reads once.
- The original Groq pilot (`734152f2719d4dd7b76033ae0260b7f7`) exposed early stops and a duplicate write. Use the new matched pilot (`5f122c6ff6934e2bb525eeb813b6a38e`) to check the revised pipeline before freezing a baseline.
- The revised pilot recorded one completed oracle pass (T01/A) and seven episode-level HTTP 429 errors. T01/B logged 17 verifier calls and zero automatic retries on writes flagged for replanning. Both D episodes stopped at the provider rate limit before tool execution. No complete matched comparison is available.

## Next

Review the Phase 7 changes and scripted batch on `siddharth/phase7-harness`.
After review, validate one small matched Gemini batch before freezing the Phase 8
config. Continue the original Section 10 baseline; see `docs/decisions.md`.

## Phases after that

8 first real experiment · 9 scale the environment · 10 ablations · 11–12 τ-bench (optional) · 13 analysis and paper.
