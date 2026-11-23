# Decisions

## Primary Phase 8 rule and additional-seed validation (2026-11-22)

- Shivam accepted retaining the original qualified supplier rule for the primary
  baseline and testing T08/T10/T16/T18 with additional seeds before full collection.
  Keep suspension_only as a separately labelled alternative, not pooled data.
- Use additional fault seeds 12/23 with fixed model generation seed 7 for readiness.
  Clean repeats measure stability; they are not independent random model samples.
- Retain solvable task failures as results. Do not remove T18, relax a rule or tune
  prompts merely to raise scores during baseline collection. Primary full config
  is prepared for all 20 tasks, A–D, fault seeds 7/12/23 at rate 0.25.

## Supplier standing rule variant (2026-11-22, pending team review)

- Shivam: "there should be a correct distinction made between suspended and not
  suspended". He proposed removing supplier approved/unapproved as a purchase
  criterion, while keeping suspension as a prohibition, if this preserves the
  verification research goal. He also requested tests beyond repeatedly failing T18.
- Retain the original qualified benchmark as the default. Add an explicit
  vendor_rule=suspension_only alternative: supplier approval is ignored, eligibility
  and non-suspension remain required. Manager approval of purchase orders, budgets,
  expiry, quantities, duplicate prevention and recovery rules are unchanged.
- Apply the rule consistently to task goals, observed response contracts, summary,
  policy diagnostics, verifier, oracle and reference/negative controls. Omit the
  unused supplier-approval field from variant public responses before injection.
  Retain legacy state metadata and original dataset/recorded outcomes.
- In alternative T18, V2/QY2 is the cheapest legal replacement; the negative uses
  suspended V3. The variant is separately labelled in configurations and dashboards.
  A higher score under a weaker supplier rule is not model/verifier improvement.
  Freeze one business-rule definition before the final baseline; do not pool modes.

## Observed evidence presentation (2026-11-22, pending team review)

- Shivam requested reducing avoidable environment/summary difficulty before judging
  Qwen. Use a compact shared observed record with vendor standing, quote links,
  order lifecycle and explicit missing-information reads. Keep full observations
  in logs and give the same scaffold to every policy.
- Explain deterministic schema/arithmetic failures with specific reasons, and log
  disagreement with the LLM verdict. Do not silently turn the verifier into a
  hybrid rule/LLM decision or force a successful final state.
- Add controlled decision-critical faults and harmless-observation controls.
  Fault exposure, detection, correction and final outcome are separate quantities;
  an injected observation fault alone does not mandate oracle FAIL.

## Local validation changes (2026-11-20, pending team review)

- Shivam: "In a real-world scenario, a company or person would cancel a problematic
  order because accepting it would cost too much." Remove positive order-creation
  caps from procurement tasks so cancelled drafts can be replaced. Retain zero caps
  where the task forbids creating orders, and retain active-duplicate checks.
  Shivam selected "Recovery allowed; defer cancellation fees". No fees are added.
- Validate observation faults using decision-critical controls rather than forcing
  every corrupted response to produce failure. The oracle still checks true state.
- Make reports readable directly from logs, with no report-generation model calls.
  Report injected-corruption diagnostics separately from genuine tool errors and
  historical concerns. Do not invent agent reasoning or attribute every failure to faults.
- Local pilot settings explicitly specify context, response limits, temperature,
  model seed and thinking. Context capacity is different from an API billing quota;
  bounded steps/responses remain operational safeguards. Retain prior run artifacts.
- Verifier contracts/observable diagnostics are identical across B/C/D, with valid
  intermediate workflow guidance. Persistent argument errors replan rather than retry
  unchanged. These behavior changes require new runs and are not retroactive results.

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
- 2026-11-05: A new branch can start from any branch, not only `main`; the AI asks which one. Reason (Krish): "maybe they want to start from another branch." Pending team review.
- 2026-11-05: Before each commit, the AI tests the person on what was just built in that step, and commits only when they get it (`repo_instructions.md` §3b). This replaces a separate rule "don't push what you can't explain". Reason (Krish): if we test before each commit, the person knows the thing. Pending team review.
- 2026-11-05: At the end of each task, the AI gives a ready-to-paste start message for the next chat (branch, folder, files to read, last commit, exact next step, "Never push, only I push"). Reason (Krish): so whoever does the next task can start the new chat properly. Pending team review.
- 2026-11-05: Git and `PROGRESS.md` are the shared truth; `HANDOFF.md` is personal. The AI checks GitHub for newer work before starting, looks at branches and unsaved changes before making a branch, and puts the start message for a different person in `PROGRESS.md`. Reason (Krish): if I did the last work, a teammate's handoff and progress will be different from mine. Pending team review.
- 2026-11-05: `repo_instructions.md` changes only through its own pull request with nothing else in it. The first repo-setup pull request (`krish/repo-structure`) is the one exception: it brings the rules in together with the new layout. The Groq code was moved out of it into `krish/groq-provider`. Reason (Krish): rules will only be changed by a separate PR. Pending team review.
