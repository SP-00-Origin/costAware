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

### Additional-seed readiness completed — 2026-11-22 (latest)

- Shivam accepted original qualified supplier rules for the primary baseline;
  suspension_only remains optional/separate. Ran T08/T10/T16/T18 under A–D with
  fault seeds 12/23, clean and 0.25 faults: 64 episodes. Qwen qwen3:8b, context 8192,
  temperature 0, thinking false, fixed generation seed 7; no source/settings tuning.
- Clean 5530d3bc5ba34b73b235e172cd4a45db: A 2/8, B 6/8, C 4/8, D 6/8.
  Verifier calls A/B/C/D: 0/102/34/40.
- Faulted 53870601f195413286d914336704838d: A 2/8, B 4/8, C 5/8, D 5/8.
  Verifier calls 0/117/40/59; selected original actions 0/104/37/48. Retry rechecks
  explain the difference. Corrupt original actions selected/exposed: A 0/17,
  B 17/17, C 7/20, D 17/18. Accepted corrupt checks/checked: B 2/23, C 1/9, D 3/22;
  A has no checked-observation FNR. These diagnostics do not establish recovery.
- All 64 action sequences replay exactly. Independent oracle verdict/diff, policy
  trigger decisions and recorded counters reproduce. Model/source/task identities
  match between clean/faulted batches. Zero provider/verifier errors or agent context
  warnings; peak agent input 5322. No LLM acceptance of failed deterministic checks
  recorded; plausible corruptions and unsafe decisions can still be accepted.
- Manually reviewed examples: T08/23/B warns about suspended supplier but agent
  releases anyway; T16/23/B cancels bad supplier order and replaces with V1, but
  quantity 30 vs required 20 still FAILs. T16/23/C PASSes despite skipped corruptions.
  T10/12/A can reject an expired quote using its remaining status field; T10/23/A
  PASSes when release response loses po_id but real release succeeds. All 16 new
  T18 cases FAIL; this remains a model/business-rule limitation, not a missing option.
- Reports: output/multiseed_validation/review.md, review.json, failure_review.md;
  auditor output/audit_multiseed_validation.py. Dashboard updated. Four selected
  medium/hard tasks and two fault seeds are not a full baseline or superiority proof.
- Prepared/validated experiments/configs/phase8_ollama_baseline.json: original rule,
  all 20 tasks × A–D × fault seeds 7/12/23 = 240 episodes at fault rate 0.25, same
  local model/options and max 30 actions. This full baseline has NOT been executed.
- Remaining Phase 8 work: archive/freeze code/model/task/config identities; collect
  the full primary grid; audit full data; produce final table/plot and paired CIs;
  complete expanded Pareto/cost/budget analysis and honest local monetary treatment;
  write short results/failure/reproduction report. Plot/paired code exists, but
  not every expanded-plan metric or confidence interval is implemented.
  Checklist: output/PHASE8_REMAINING.md. Branch/commit decisions still deferred;
  no commits/pushes. Latest source suite remains 450 pass; this step added configs
  and analysis artifacts, not production-code changes.

### Supplier rule option and broader task tests — 2026-11-22 (preceding step)

- Shivam proposed removing supplier approved/unapproved as a purchase criterion
  while retaining suspension, and requested other tasks. Only original T18 has an
  unapproved but nonsuspended vendor. Supplier approval is retained in default
  qualified mode; new explicit suspension_only mode ignores it but still requires
  eligibility/non-suspension and all purchase-order manager approvals and other rules.
- src/environment/variants.py transforms task copies, not tasks/tasks.jsonl. T18's
  alternative reference/expected vendor becomes V2; negative becomes suspended V3.
  Public variant vendor responses omit supplier approved before fault injection.
  Agent/verifier summaries, diagnostics and oracle use the same declared rule.
  Batch configs, outcomes and dashboards label the mode; old logs remain original.
- All 450 offline tests pass, including reference/negative controls for all 20 tasks
  under the alternative, default-rule preservation, suspended/ineligible rejection,
  input contracts and metadata. No dependencies added; all changes uncommitted on main.
- Original-rule broader pilot T08/T10/T16, all A–D, seed 7, clean and faulted:
  b0d39f043ade49e68822b719b8ea48d0 (clean 9/12),
  5f55d05fca244dab878cce3741422eef (faulted 4/12).
  T08: A FAIL, B/C/D PASS in both conditions. T10: clean all PASS; faulted only C
  PASS. T16: clean B/D PASS, A/C FAIL; faulted all FAIL. T10 stale quotes falsely
  show an expired quote as active; A/B/D buy it. T16 bad choices use suspended V2.
  No context warnings/provider/verifier errors; peak agent input 4674 at 8192.
- Fresh T18 rule comparison with identical code/model/settings across all batches:
  qualified clean 5f308ce737e14d0b85464a4ff455e450 and faulted
  928a90d36ec5420283f95f9bbbb09498: all 8 FAIL.
  suspension_only clean 7bb5a64591024fce929488b2e7f12169 and faulted
  c7151227651e44b28c3c34c922611152: all 8 PASS. All select V2, which is legal only
  under the alternative. This is a changed success rule, not improved verification.
  No context warnings/provider/verifier errors; peak agent input 4108.
- All 40 new action trajectories replay, and independent oracle verdict/diff match
  recorded task snapshots. Old 24 diagnostic episodes also reproduce after adding
  opt-in rules. Audits/reviews: output/supplier_diagnostic_pilot/ and
  output/vendor_rule_comparison/. Dashboards updated and modes labelled.
- Next: choose/freeze the company's supplier rule, investigate quote-validity checks
  and suspended-supplier recovery across more seeds, then prepare the 240-episode
  baseline. Do not pool the two rule modes or infer superiority from one seed.
  Nothing committed/pushed. Pending rule decision is in docs/decisions.md.

### Compact evidence and specific diagnostics — 2026-11-22 (preceding step)

- Shivam approved the environment/input improvements after discussing why a fault
  need not cause final-state failure. Replaced repeated vendor assessments with one
  observed vendor record, quote links, order lifecycle/quantity/approval IDs, budget
  remaining and explicit next status reads. Failed status reads invalidate a prior
  usable summary. Raw observations/provenance remain in the trajectory.
- Clarified profile/status tools, supplier vetting, cancellation and approval
  arguments. Shared agent prompt is 311 words vs 528; summaries on the same archived
  T18 traces shrink about 42–47%. Identical scaffolding applies across A–D.
- Deterministic validation now emits exact field/arithmetic/status reasons. Existing
  boolean policy checks use those reasons; LLM verdicts remain separate and are not
  overridden. Reports show diagnostics and explicit LLM/diagnostic disagreement.
  Runtime fingerprints now include tool descriptions in src/environment/tools.py.
- Offline suite: 420 pass. New controlled graph cases show a false vendor-approval
  observation -> bad purchase -> FAIL when trusted, and a recheck -> valid purchase
  -> PASS. A separate false write-response quantity control still correctly PASSes
  when the real released order remains correct. These are stand-ins, not Qwen claims.
- Matched Qwen qwen3:8b 8K, seed 7 pilot: clean
  4da7b1351d0d4bbf96f6d41e23e39ba4 and faulted 4f8a1e65c02644cc8980176a0d5665eb.
  Each passes 8/12: T01/T14 all policies PASS, T18 all FAIL. All 24 action sequences
  replay and independently recomputed oracle verdicts/diffs match. Reports rebuilt.
- No provider/verifier errors or agent context warnings. Peak agent/verifier input
  3828/2055. The T01 arithmetic fault is now detected when selected under B/D;
  no logged LLM acceptance of a failed deterministic check in this pilot.
- T18 now checks V1 and V2 but still buys from unapproved V2. Verifier sometimes
  treats vendor approval as if purchase-order manager approval could resolve it.
  The oracle correctly rejects that state. Shorter inputs have not solved this
  semantic error; do not claim overall verification correctness from zero diagnostic
  disagreements. One seed cannot establish policy superiority or causal improvement.
- Latest Policy A fault counts: T18 one/FAIL, T01 three/PASS, T14 one/PASS. These
  differ from the preceding pilot because the agent's tool choices changed.
- Artifacts: output/compact_evidence_pilot/review.json and review.md;
  output/audit_compact_evidence.py. Source changes uncommitted on main; no push.
  Next review supplier-approval interpretation and agree a fixed model/reasoning
  comparison before the full 240-episode baseline. Do not tune task-specific answers.

### Environment/input audit — 2026-11-22 (after guidance pilot)

- Policy A in the latest faulted batch: T18 zero injected faults/FAIL, T01 three/PASS,
  T14 two/PASS. A disables the separate verifier, but its agent still makes status
  rechecks. Corrupted display values did not necessarily affect real final state.
- All 20 task reference/negative controls validate again. An additional T18 route
  chooses vendors using observations only and passes: V1/QY1 costs 10350 against
  40000 available budget; 8000 is an approval threshold. Tasks are solvable.
- Confirmed input limitations: repeated nested vendor facts; partial vendor-profile
  results require a separate standing check; summary omits order lifecycle status
  and explicit next reads. Clean T18 A/B/C leave V1 status unknown rather than check it.
- Confirmed verifier errors: B/D ignore a true arithmetic/schema diagnostic on T01
  quotes; clean T18/B mistakes truthful bad standing for faulty output and confuses
  approval threshold with budget in a warning. Do not attribute all failures to faults.
- Audit/report and recommendations: output/environment_setup_review.md. Next discuss
  simpler observed-only evidence, lifecycle/approval guidance, specific diagnostics
  and controlled decision-critical faults before another live comparison. These
  presentation issues are confirmed, but their causal impact requires an ablation.
  No experiment logic changed during this audit; no commits or pushes.

### Shared vendor guidance validation — 2026-11-22 (preceding pilot)

- Shivam approved adding observed-only usable/unusable/unknown vendor assessments,
  quote/order vendor links, price-ranking clarification and explicit draft recovery
  guidance. These are shared by A–D; only verification timing differs. Missing or
  non-boolean status is unknown, an explicit bad flag is unusable, and all three
  required flags must be observed for usable standing. No truth lookup, automatic
  action blocking, vendor substitution or oracle change was added.
- New 8K, Qwen qwen3:8b, seed 7 pilot on T18/T01/T14 under A–D:
  clean d1baaad7d17b4388a1551162618a8ea7 passes 8/12;
  fault rate 0.25 d5311caf808345cf8184dee48779af75 passes 7/12.
  T18 fails all eight episodes. T01/T14 pass all clean episodes; faulted T01/D
  fails after invalid approve_order arguments and incomplete approval/release.
- T18 clean D releases a valid V1 replacement but leaves an invalid V2 draft active:
  vendor standing and duplicate checks correctly fail. Faulted B cancels the bad
  draft and creates V1 but stops before approval/release. Correct warnings do not
  guarantee that the agent completes recovery or the whole task.
- Four agent context warnings occur in faulted T18 (B: three, D: one); maximum
  reported agent input 8049 at 8192 context. No provider or verifier errors. Context
  pressure remains for long histories; clean T18 also fails without such warnings.
  A configured fault rate does not guarantee faults in every episode (T18/A has zero).
- Validation: 404 offline tests pass, including shared agent/verifier input checks
  and controlled warning ignored/followed tests. All 24 action sequences replay
  exactly, and independent final-state oracle evaluations reproduce every verdict
  and diff using each run's task snapshot. Reports/dashboard rebuilt from the logs.
  Audit: output/vendor_guidance_pilot/review.json; output/audit_vendor_guidance.py.
- Work remains uncommitted on main; branch/commit choices deferred by Shivam.
  No full 240-episode baseline started. Next: review remaining completion/argument
  failures and context pressure, then agree a matched model/runtime comparison
  before freezing the Phase 8 configuration. These one-seed pilots cannot establish
  policy superiority. Do not retroactively replace previous runs or oracle outcomes.

### T18 evidence and context investigation — 2026-11-22

- Working on the current main checkout as requested; branch/push decisions deferred.
  Added an observed-only vendor evidence summary shared by agent A–D and verifier
  B/C/D, quote/order-to-vendor links, explicit independent flag/ID instructions and
  regression tests. No hidden state, automatic vendor substitution or oracle changes.
- Restarted the existing Ollama background processes with D:/Ollama/models. The model
  files were intact; the previous server saw no models. Setup-error run
  52b02fa37c214ae1948123eb6c6ce01b has four model-not-found errors, no tool actions.
- New fixed-code T18 pilot: A–D, seed 7, clean/faulted at 8192 and 16384 context.
  Runs: 5973aacbb4d34e0e93a632fb35b9701a (8K clean),
  765a8887b0f740c4ad2473f973bf3477 (8K faulted),
  81248027e571447ba94172e6e081768b (16K clean),
  80c5e3ffaf154330b3d794853ff67186 (16K faulted).
  All 16 oracle FAIL; all trajectories replay exactly. No verifier errors or
  near-context warnings in these runs; peak input 5456 tokens. Larger context
  did not solve this task. At 16K, ollama ps reported 20% CPU / 80% GPU offloading.
- The agent now discovers the existing order rather than inventing its vendor ID,
  but still selects an unapproved replacement. Some verifier calls correctly flag
  that violation; the agent can still continue. compare_quotes ranks prices and
  does not vet suppliers. This remains a model decision/adoption limitation, not a
  corrected live task outcome. No full Phase 8 baseline started.
- Pilot audit: output/vendor_context_pilot/review.json. Tests: 390 passed.
  Ollama server was started in the background (PID 11596); log path in output/.

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


## Phase 8 baseline completed on 2026-11-23

- Done by Shivam. Original qualified supplier rules, Qwen3 8B, all 20 tasks,
  policies A–D, fault seeds 7/12/23, fault rate 0.25. Run d57331709a6f43088a2b58faf01093ab.
- All 240 outcomes present. Passes A 32/60, B 36/60, C 36/60, D 37/60.
  Verifier calls 0/648/245/321. D–B success difference +1.7 percentage points,
  task-cluster 95% interval −3.3 to +8.3. These results leave reliability ranking open.
- Independent audit replayed 2,473 tool events and matched oracle, router and
  workload counters. All 20 reference/negative/empty controls behave as expected.
  Full offline suite 450 passed. Zero verifier errors and agent context warnings.
- One baseline timeout, T13/D/7, coincided with Modern Standby. Kept in the
  primary denominator. Separate diagnostic repeat e1fd3d57c5574d50a910f76f3a95c9b9
  passed in 31.6 seconds. Timing sensitivity removes the same block for all policies.
- Thirty of 32 overlapping pilot cases agreed. Fixed model settings do not
  guarantee identical generations. No pilot outcomes pooled into the baseline.
- experiments/audit_phase8.py rebuilds intervals, frontiers, episode index and
  chronological evidence. Run folder contains freeze.json, baseline_source.zip,
  audit.json, episode_review.md, phase8_report.md and dashboard.html.
- Editable manuscript docs/costAware_Research_Report.docx
  records setup, metrics, outcomes, failures, uncertainty and references.
  All text/tables/chart are editable and black. Local electricity/ownership
  costs are unmeasured. Mean-budget envelopes compare whole policies.
- Next is Phase 9 planning for declared task/model expansion. Keep this baseline
  frozen and review failures and repeat variability before selecting that grid.
  Changes remain uncommitted on main. Shivam decides branch/commit destination.

## Continuing research report revised on 2026-11-23

Renamed the manuscript to costAware_Research_Report.docx. Expanded the hypothesis, focused literature review through 23 November 2026, distinctions from prior work, and interpretation of workload savings versus unresolved reliability and periodic-policy comparisons. All-black native editable content verified. No experiment results changed.


## Phase 8 baseline finalized with full replication on 2026-11-23

- Shared release prepared in results/phase8_qwen_baseline with a README,
  standalone dashboard, summaries, comparison JSON and verified frozen ZIP.
  Local output scratch files are outside this shared release.

- Done by Shivam. Full 20-task × A–D × three-fault-seed replication:
  fbe4b0bd3309497da33ee617c1fe2983. Source/model/task/config identities match
  initial d57331709a6f43088a2b58faf01093ab. No generation tuning during collection.
- A/B/C/D passes 33/37/36/38 of 60. Verifier calls 0/642/241/322.
  D saves 49.8% calls vs B. D–B success delta +1.7 percentage points with
  task-cluster 95% interval 0.0 to 5.0. No declared noninferiority margin.
- All 240 outcomes present, 2,464 executed calls replay exactly, oracle/router/
  counters agree, controls pass. No runtime/verifier errors or agent context warnings.
  Offline suite 450 passed. Results unchanged by document updates.
- 235/240 outcomes agree with initial collection. Four become passes (including
  T13/D/7 standby timeout), one T17/C/12 becomes fail for unfinished approval/release.
  Both complete cohorts retained. Same fixed settings do not ensure identical model actions.
- Revised docs/costAware_Research_Report.docx generalizes the problem statement,
  distinguishes procurement as the tested domain, maps H1–H4 to evidence,
  records the 17th tool and safe recovery distinction, and updates every main table.
  Original case studies are explicitly labeled with the initial run identity.
- Baseline evidence and frozen report under the replication folder. The verified
  costAware_frozen_baseline_<run>.zip bundle contains both cohorts, source archives,
  manifests, raw logs, audits, comparison rows and editable report.
- Next per original plan: Phase 9 expands native tasks/trials/models, optional
  fault-rate sweep. Recommend full matched clean control and held-out task design.
  Phase 10 ablates D triggers and tests matched-budget random selection.
  Phases 11–12 optional external benchmark pilot/comparison; Phase 13 final
  statistics, failure taxonomy and clean-machine reproduction.
- Source changes remain uncommitted on main. Shivam decides commit/branch and pushes.
