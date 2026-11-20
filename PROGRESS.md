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
| 7 | Core config-driven harness, JSONL/parser, metrics, dashboard and readable traces; final engineering gate passed 2026-11-21 | Siddharth; Shivam (local validation) | `experiments/`, `src/evaluation/`, `docs/PHASE7_CHECKS_AND_PHASE8_START.md` |

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

### Phase 7 final check and documentation — 2026-11-21

- On Shivam's request, use existing `shivam_branch` (exact spelling), fast-forwarded
  from 4421c65 to the already fetched main commit c511c37, preserving all work.
- Final offline gate: 387 tests passed, all 20 tasks validated, and scripted run
  `4d289b3ea7fb4bcfbd64b1354cf9d9f2` completed 16/16 episodes with oracle PASS.
  Reports rebuilt from JSONL with unchanged summaries; all 16 trajectories replayed
  exactly. This completes the original Section 10 Phase 7 engineering criterion,
  not every cost/budget feature of the expanded metrics plan.
- README rewritten around the problem, setup/policies, simulation and providers.
  Added `docs/edits/EXPERIMENT_SETUP_CHANGES.md`, `docs/OLLAMA_SETUP.md`,
  `docs/RUN_COMMANDS.md` and `docs/PHASE7_CHECKS_AND_PHASE8_START.md`.
  Local documentation links resolve and documented CLI entry points were checked.
- Phase 8 startup is documented, not executed: review T18/context behavior, agree
  acceptance and runtime settings, validate multiple seeds, then freeze the first
  20-task × four-policy × three-seed baseline. Existing Gemini config has 240 episodes;
  a local-Qwen baseline config has not yet been frozen.

### Implemented local validation improvements — 2026-11-20

- Shivam approved recovery replacements and deferred cancellation fees. Procurement
  tasks no longer have positive creation caps; explicit zero caps and active duplicate
  checks remain. Task data was regenerated and all reference/negative tests pass.
- Added native Ollama requests with explicit 8192 context, agent/verifier response
  limits 2048/1024, temperature 0, model seed 7, thinking off and bounded timeout.
  Groq/Gemini and other providers remain. Optional total-token budgets stop between
  episodes; they are not hard spending caps. Local validation has no aggregate cap.
- Verifiers share tool contracts and observable checks across B/C/D, with valid
  workflow guidance. Persistent argument errors replan without identical retries.
  Shared agent instructions distinguish vendor properties, approval and release.
- Reports now show readable per-action scenarios and raw records: observations,
  selection reasons, verdicts, retry/replan instructions, next actions and offline
  corruption differences. No report-generation model calls or invented reasoning.
  Outcome/diagnostic labels and denominators are clearer; true tool errors are separate.
- New headers retain task snapshots, dataset/source hashes, resolved settings and
  local model identity. Historical oracle verdicts are not re-evaluated when rendering.
- Validation: 387 offline tests passed. New clean run
  `85d027114e304d58b6165fcaa551016c` and faulted run
  `dc07f0703a9d4805ab481c482f8c99d0`: 20 episodes each, A/B/C/D each pass 4/5
  in both conditions; clean verifier calls 0/45/14/15, faulted 0/71/19/27.
  All 40 trajectories and oracle diffs replay from recorded task snapshots;
  zero provider/verifier-format errors. T18 fails under every policy, including clean.
- Combined review: `output/qwen_validation_v2_review/index.html`, with audit JSON.
  The only source fingerprint difference across batches is llm.py input validation
  rejecting non-mapping options; actual resolved settings, prompts and graph match.
- Remaining: T18 vendor/evidence tracking is unreliable. Faulted T18/B reports five
  near-context calls at 8192 capacity. Review these before a full baseline; one-seed
  validation cannot establish policy superiority. Changes remain uncommitted on main.

### Local Qwen pilot — 2026-11-20

- Shivam requested a local Qwen run before deciding where to commit the changes.
  Added `ollama` alongside all existing providers on the current `main` checkout;
  changes remain uncommitted. No branch was created and nothing was pushed.
- `experiments/configs/phase8_ollama_pilot.json` matches the Gemini pilot grid:
  T01/T11, A–D, seed 7, fault rate 0.25, max 30 actions, model `qwen3:8b`.
  Agent and tool-free JSON verifier use separate local clients. Thinking is disabled.
- Run `49593c0bab404216bed50ace7fbb3113`: all eight episodes completed with oracle
  PASS; zero provider/verifier errors. A/B/C/D verifier calls: 0/24/8/8.
  T01/B ended with `gave_up` despite an oracle-passing final state; inspect its trace.
- Raw JSONL, summary, paired comparisons and dashboard are under
  `output/experiments/49593c0bab404216bed50ace7fbb3113/`; `output/dashboard.html`
  includes this run. These are generated local outputs, not files to commit.
- Runtime: RTX 4060 Laptop, Qwen Q4_K_M digest `500a1f067a9f`, 4,096-token context.
  This is a two-task feasibility pilot, not a full baseline or reliability conclusion.
- Validation in `costaware_env`: 355 tests passed; `git diff --check` passed.
  Next: review the pilot and context needs, then decide the branch/commit destination
  before freezing or running a larger baseline. Groq and Gemini configs remain available.
- Audit follow-up (2026-11-20): all eight trajectories replay identically, oracle
  results reproduce, policy decisions and independently counted confusion metrics
  match the saved reports. All 40 modified-final-state negative controls are rejected;
  355 tests pass again. Local audit artifacts are under `output/`.
  False-positive labels measure absence of injected corruption, not necessarily
  unjustified suspicion (tool errors/history conflicts can be counted).
  T01/B's final prompt approaches the 4096-token context limit; context-related
  loss is not established by the saved logs. Do not infer verifier misses are due
  to context: their prompts were well below that limit.
- Expanded Qwen review (2026-11-20), run `aad413e9cc96469fb300c1c5bbb10bbb`:
  T05/T14/T18 under A–D, same seed 7 and settings, 12 finished episodes.
  Combined with T01/T11: A 4/5, B 3/5, C 4/5, D 4/5 oracle passes;
  verifier calls 0/53/23/27. All T18 policies fail; T14/B also fails.
  No provider/verifier errors; real tool errors and agent mistakes are recorded.
- Combined audit/dashboard: `output/qwen_collective_review/`. All 20 trajectories
  and oracle diffs reproduce, five clean reference solutions pass, 63 altered
  successful final states are rejected. 355 tests pass. No model prompt, policy,
  recovery or metric behavior was changed during this review.
- Findings: T14/B stops with an APPROVED rather than RELEASED order. T18/A selects
  an unapproved vendor despite clean evidence; B gets stuck on an invented vendor ID;
  C/D retain the old order and create an invalid replacement. D's corrupted status
  observations also provoke a failed cancellation attempt. These are not all caused
  by injected faults. Context pressure affects longer B/C/D trajectories; exact
  content loss is not established by the logs. Review verifier semantics, metric
  interpretation, persistent-error retries and runtime metadata before a baseline.
- Suspended-vendor controls (2026-11-20): 12 deterministic graph checks on T08
  confirm warning ignored -> suspended-vendor order -> oracle FAIL; warning followed
  under B/C/D -> valid-vendor order -> PASS; selected but verifier misses -> FAIL.
  These use test stand-ins, not Qwen performance results. Artifacts:
  `output/suspended_vendor_controls/summary.json`.
- Acceptance-rule finding: cancel a bad T08 draft, create a valid replacement,
  approve/release it -> all other oracle checks pass, but `max_new_orders=1` fails
  because cancelled orders still count as created. With cap 2 the same state passes.
  The actual task was not changed. Review whether bounded corrective replacements
  should be permitted before interpreting recovery performance; preserve active
  duplicate prevention. Details: `output/suspended_vendor_controls/recovery_limit.json`.

Review the local validation changes and readable T18 traces, decide the branch/commit
destination, and resolve the context/evidence limitations before freezing a larger
Phase 8 baseline. See `docs/decisions.md` for the pending team-review decisions.

## Phases after that

8 first real experiment · 9 scale the environment · 10 ablations · 11–12 τ-bench (optional) · 13 analysis and paper.
