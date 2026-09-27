**Cost-Aware Adaptive Verification  
for Long-Horizon LLM Agents**

**UPDATED PHASE-WISE IMPLEMENTATION PLAN**

*Environment: Synthetic Enterprise Procurement & Operations  
Team: 3 members \| Orchestration: LangGraph  
Primary: Custom deterministic simulator \| Optional: τ-bench validation track*

This version replaces the earlier e-commerce environment while preserving the original research question, Policies A–D, fault injection, self-verification, recovery, deterministic oracle, logging, ablations, and reliability-vs-verification-budget evaluation.

# Important principle

This is a research testbed, not an enterprise procurement product. Complexity must create meaningful verification decisions—not random confusion. The simulator retains hidden ground truth so task success is always machine-checkable.

# 1. Research Anchor

Primary question: Can a long-horizon, tool-using LLM agent dynamically decide when to verify its own actions using cheap, explainable risk signals, keeping reliability close to verify-everything while paying a fraction of the verification cost?

| Hypothesis | Implementation target                                                                                                                       |
|------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| H1         | No verification becomes more vulnerable as horizon/faults increase.                                                                         |
| H2         | Verify-every-step improves reliability but has high verification overhead, latency, and token cost.                                         |
| H3         | Adaptive Policy D attempts to approach B's reliability with substantially lower verification overhead.                                      |
| H4         | State-changing/high-risk actions and schema/sanity failures should be especially valuable triggers; confidence remains an ablatable signal. |

## Core flow

> Task → LangGraph Agent → Tool → Fault Injector → Policy A/B/C/D  
> → (optional Self-Verifier) → Recovery → Next Step  
> → Deterministic Oracle → Logs → Metrics

# 2. New Environment — Synthetic Enterprise Procurement & Operations

A simulated enterprise procurement/operations world, intentionally separate from the team's AegisOps/FaultForge infrastructure project. No Kubernetes, Prometheus, microservice health monitoring, or DevOps remediation is required.

| Entity            | Key state                                                             |
|-------------------|-----------------------------------------------------------------------|
| Vendor            | id, eligibility, approval/suspension, preferred flag, payment profile |
| Component/Product | id, category, reference price, required quantity, availability        |
| Supplier Quote    | vendor, component, unit price, quantity, expiry, shipping, status     |
| Project           | id, owner, procurement rules, priority                                |
| Budget            | allocated, spent, reserved, remaining                                 |
| Purchase Order    | id, vendor, items, total, status, approval, release state             |
| Approval          | level, requester, approver, status, validity after changes            |
| Invoice           | id, PO, amount, line items, mismatch/status                           |
| Shipment          | id, PO, quantity, destination, dispatch status                        |

## Structured complexity

- Multiple valid paths: the correct next action depends on current state.

- State dependencies: PO creation/modification can reserve budget or invalidate approval.

- Conflicting observations: different tools may expose inconsistent records.

- Stale observations: quotes, budget views, or statuses may be outdated.

- High-impact state changes: create, modify, approve, release, cancel.

- Controlled faults: errors are reproducible and categorized.

- Hidden ground truth: the simulator knows the real state even when the agent does not.

## Example

Task: Purchase 40 units of component X for Project Alpha, use an eligible vendor, remain within budget, obtain required approval, and release the order.

> Possible path:  
> search_vendors → get_vendor_details → get_quotes → check_vendor_status  
> → check_budget → compare_quotes → create_purchase_order  
> → request_approval → approve_order → release_order → confirm

This is not a fixed script. Another state may require a discount, quote refresh, existing-order check, modification, or vendor change.

# 3. Initial Tool Set

| Tool                    | Risk         | Purpose                        |
|-------------------------|--------------|--------------------------------|
| search_vendors()        | Low/read     | Find candidate suppliers       |
| get_vendor_details()    | Low/read     | Vendor profile/eligibility     |
| check_vendor_status()   | Low/read     | Current approval/suspension    |
| get_quotes()            | Low/read     | Supplier quotes                |
| check_quote_validity()  | Low/read     | Expiry/constraint check        |
| check_budget()          | Low/read     | Budget/reserved amount         |
| check_existing_orders() | Low/read     | Existing commitments           |
| compare_quotes()        | Low/compute  | Compare candidates             |
| request_discount()      | Medium/write | Request negotiated terms       |
| create_purchase_order() | High/write   | Create PO/reserve budget       |
| modify_order()          | High/write   | Change PO                      |
| request_approval()      | Medium/write | Submit for approval            |
| approve_order()         | High/write   | Change approval state          |
| release_order()         | High/write   | Release approved PO            |
| cancel_order()          | High/write   | Cancel PO                      |
| check_invoice()         | Low/read     | Inspect invoice/PO consistency |

The high-risk tag is an actual Policy D signal, not just documentation.

# 4. State Model and Deterministic Oracle

Maintain two conceptual views: (1) true simulator state, visible only to the environment/oracle; (2) agent-visible observations, which faults may corrupt.

> TRUE STATE:  
> Vendor C: approved=False, suspended=True, quote=870, quote_expired=True  
> Budget: remaining=35000, reserved=0  
> PO: status=NOT_CREATED  
>   
> FAULTY OBSERVATION:  
> Vendor C: approved=True, suspended=False, quote=870, quote_valid=True

The oracle must never be an LLM. It compares the true final state against the task's expected state and returns PASS/FAIL plus a structured diff.

> oracle_check(final_true_state, expected_final_state)  
> → (oracle_pass: bool, diff: dict)

- Correct vendor, component, quantity and budget outcome.

- Required approval exists and remains valid after modifications.

- PO reaches the required final state.

- No forbidden/suspended vendor is used.

- No forbidden duplicate/conflicting order is created.

# 5. Fault Injector

The fault injector remains a central research component from the original methodology. It wraps tool calls, is seeded, and is unit-tested before the agent is trusted.

| Fault                     | Example                | Agent-visible effect                         |
|---------------------------|------------------------|----------------------------------------------|
| Wrong value               | Budget true = ₹35k     | Reports ₹40k                                 |
| Stale information         | Quote expired          | Old quote appears active                     |
| Contradictory information | Vendor suspended       | Profile says approved, status says suspended |
| Malformed output          | Quote object invalid   | Wrong type/missing structure                 |
| Missing field             | Approval lacks status  | Required field omitted                       |
| Timeout                   | Quote service delayed  | Timeout/no result                            |
| Incorrect status          | PO pending approval    | Tool says approved                           |
| Corrupted observation     | Reserved budget = ₹10k | Reports ₹0                                   |

- Use random.Random(seed) and log true result, observed result, and fault type.

- Do not mutate hidden ground truth unless explicitly testing state corruption.

- Match task/seed across policies where possible.

- Start around fault_rate=0.25; 0.10/0.25/0.40 is an optional sweep.

# 6. LangGraph Architecture

The source methodology recommended plain Python for maximum control. This updated plan uses LangGraph because the team has chosen it, but all research-critical nodes must remain explicit and separately logged.

> START  
> ↓  
> Initialize Task/State  
> ↓  
> Agent Decision  
> ↓  
> Tool Execution  
> ↓  
> Fault Injection  
> ↓  
> Policy A/B/C/D  
> ├─ SKIP ──────────────┐  
> └─ VERIFY │  
> ↓ │  
> Self-Verifier │  
> ↓ │  
> OK / SUSPICIOUS │  
> ↓ │  
> Recovery ───────────┘  
> ↓  
> Update State → Continue/DONE  
> ↓  
> Deterministic Oracle → PASS/FAIL

- task_id and goal

- agent-visible observations/history

- latest action and tool arguments

- latest result

- verification decision and trigger reason

- verifier verdict

- recovery attempts

- step/max-step count

- research-side fault and oracle metadata

# 7. Policies A–D

| Policy                | Rule                                                 | Purpose                              |
|-----------------------|------------------------------------------------------|--------------------------------------|
| A — No verification   | Never verify                                         | Lower-bound baseline                 |
| B — Verify every step | Verify after every action                            | High-reliability/high-cost reference |
| C — Fixed schedule    | Verify every N steps, e.g. N=3                       | Fixed-cost baseline                  |
| D — Adaptive          | High-risk OR schema/sanity failure OR low confidence | Proposed method                      |

> def should_verify(action, result, history, step):  
> if action\["tool"\] in HIGH_RISK_TOOLS:  
> return True  
> if not passes_schema_check(action\["tool"\], result):  
> return True  
> if model_confidence(action) \< CONF_THRESHOLD:  
> return True  
> return False

# 8. Self-Verifier and Recovery

The self-verifier is an extra LLM call. The deterministic oracle is separate, hidden, and used only for evaluation.

> {  
> "suspicious": true,  
> "reason": "Vendor status conflicts with previous vendor information."  
> }

1.  Re-call the same tool once.

2.  If still suspicious, re-plan with the flagged concern.

3.  If unresolved after the allowed attempts, log an unrecovered fault; do not force success.

# 9. Task Dataset

| Task family           | Example                                              | Target horizon |
|-----------------------|------------------------------------------------------|----------------|
| New procurement       | Buy components within budget from an eligible vendor | 5–9            |
| Quote conflict        | Resolve conflicting supplier quotes                  | 6–10           |
| PO modification       | Modify an existing PO after change                   | 7–12           |
| Budget constraint     | Select supplier including shipping                   | 6–10           |
| Approval workflow     | Create, approve, release                             | 6–10           |
| Duplicate prevention  | Check existing commitments first                     | 5–9            |
| Vendor-status problem | Switch from suspended vendor                         | 7–12           |
| Invoice mismatch      | Detect and resolve invoice/PO mismatch               | 7–12           |
| Discount negotiation  | Request discount to meet budget                      | 8–13           |
| Complex mixed task    | Existing PO + quote change + approval invalidation   | 10–15+         |

| Tier   | Target         | Purpose                   |
|--------|----------------|---------------------------|
| Easy   | 3–5 actions    | Validate simulator/oracle |
| Medium | 6–9 actions    | Branching + single faults |
| Hard   | 10–15+ actions | Long-horizon propagation  |

Write ~20 tasks by hand first. Only after validation, template-generate toward 50–100 and then 200 if the harness remains stable.

# 10. Phase-Wise Implementation Plan — 3-Member Team

Do not permanently assign one person to one subsystem. Work can be parallelized inside phases, but all three members should understand the full pipeline and each phase must end in visible evidence.

# Phase 0 — Freeze Updated Design

Freeze procurement environment, tools, risk tags, task schema, faults, oracle, policies, and metrics.

## Build / deliverables

Updated architecture; tool catalog; task schema; fault taxonomy; experiment config.

## Visible progress

Team can explain the new environment without e-commerce. Every feature has a research reason.

## Exit criterion

No unresolved core decisions; no premature ML risk model.

# Phase 1 — Deterministic Simulator

Build entities, state transitions, tools, reset/init, and unit tests.

## Build / deliverables

Runnable simulator; tool registry; initial-state generator; tests.

## Visible progress

A task runs by direct Python calls with deterministic state.

## Exit criterion

At least 10 representative tasks execute correctly.

# Phase 2 — Tasks + Oracle

Write ~20 tasks, difficulty tiers, JSONL, and objective oracle.

## Build / deliverables

tasks.jsonl; oracle; reference trajectories.

## Visible progress

Oracle distinguishes success/failure without an LLM.

## Exit criterion

20 validated tasks; oracle never depends on model judgment.

# Phase 3 — Fault Injector

Implement seeded faults and unit tests before the agent.

## Build / deliverables

Injector; replay mechanism; fault tests.

## Visible progress

Same seed reproduces same fault; true vs observed result are separable.

## Exit criterion

All core fault types pass tests.

# Phase 4 — LangGraph Agent

Build tool-using agent on clean environment first.

## Build / deliverables

Graph; state; structured tool calls; step limit.

## Visible progress

Agent completes a meaningful subset of clean tasks.

## Exit criterion

No infinite loops; DONE works; trajectories inspectable.

# Phase 5 — Verifier + Recovery

Add self-verifier and controlled recovery.

## Build / deliverables

Verifier node; recovery node; logs; demos.

## Visible progress

Injected fault → verify → suspicious → recover → oracle PASS can be shown.

## Exit criterion

Recovery behavior is identical across policies.

# Phase 6 — Policies A–D

Make verification timing the experimental variable.

## Build / deliverables

Policy module; config; tests.

## Visible progress

Same task/model/seed runs under all four policies.

## Exit criterion

Only verification timing changes.

# Phase 7 — Logging + Harness

Automate batch experiments and complete logging.

## Build / deliverables

Runner; JSONL; parser; config.

## Visible progress

One command generates a complete small experiment.

## Exit criterion

No manual spreadsheet copying.

# Phase 8 — First Real Experiment

Run 1 model × 4 policies × 20–50 tasks × 3–5 trials.

## Build / deliverables

First reliability-vs-overhead plot; first results table.

## Visible progress

You have the first genuine research graph, not just a module demo.

## Exit criterion

Full run from config to plot.

# Phase 9 — Scale Native Environment

Increase tasks/trials/models only after stable baseline.

## Build / deliverables

Stable dataset; cross-model results; optional fault-rate sweep.

## Visible progress

No missing logs and matched tasks/seeds across policies.

## Exit criterion

Reproducible baseline grid.

# Phase 10 — Ablations

D; D−risk; D−schema; D−confidence; D+matched-budget random.

## Build / deliverables

Ablation table + plot.

## Visible progress

You can explain which signals contribute and whether placement matters.

## Exit criterion

Same tasks/seeds/faults/recovery across variants.

# Phase 11 — τ-bench Pilot

Add τ-bench only after native baseline works; instrument verification if compatible.

## Build / deliverables

Adapter prototype; compatibility notes; small pilot.

## Visible progress

Same agent can be tested with verification OFF/ON where the harness allows it.

## Exit criterion

Do not let τ integration delay native experiment.

# Phase 12 — Native vs τ-bench

Keep results separate; compare what each environment lets you measure.

## Build / deliverables

Two-track evaluation table; limitations.

## Visible progress

Clear distinction between controlled research evidence and external validation.

## Exit criterion

No invalid mixing of different benchmark metrics.

# Phase 13 — Failure/Stats/Reproduction/Paper

Failure taxonomy, CIs, paired comparisons, final figures, clean rerun, paper/demo.

## Build / deliverables

Final paper, repo, figures, taxonomy, reproduction guide.

## Visible progress

Every major claim traces to logs.

## Exit criterion

Clean-machine reproduction succeeds.

# 11. τ-bench: With vs Without

The source document mentions τ-bench in related work; it does not define a separate 'τ tool'. In this plan, τ-bench is treated as an external benchmark track, not a core environment tool.

The original τ-bench is a Tool-Agent-User Interaction benchmark with structured domain tools and state-based task evaluation. Its repository currently warns that the original tasks are outdated and points toward newer τ-family releases. Therefore, if used, record the exact benchmark version/domain/task set.

| Dimension       | WITHOUT τ-bench                                | WITH τ-bench                                                           |
|-----------------|------------------------------------------------|------------------------------------------------------------------------|
| Environment     | Custom procurement/operations simulator        | Benchmark-provided environment                                         |
| Control         | High: you control state, faults, tasks, oracle | Lower: benchmark controls environment/task protocol                    |
| Fault injection | Native, central independent variable           | Requires compatible instrumentation; not automatically equivalent      |
| Ground truth    | Your deterministic oracle                      | Benchmark state/goal evaluation                                        |
| Domain          | Procurement/operations                         | τ-family domains such as retail/airline; newer versions may add others |
| Purpose         | Primary research testbed                       | External validation/generalization                                     |
| Difficulty      | You control 3–15+ step tasks                   | Benchmark-defined                                                      |
| Reproducibility | You control seeds/faults/tasks                 | Depends on benchmark/user-simulator/model/version                      |
| Cost            | Can stay laptop-scale with local models        | May require additional model calls/setup                               |
| Interpretation  | Main evidence for the proposed mechanism       | Supporting evidence if integration is valid                            |

## Recommended order

4.  Finish native simulator + A–D baseline first.

5.  Add τ-bench only after the native experiment is reproducible.

6.  Pilot a small τ-bench run with verification OFF/ON if instrumentation is possible.

7.  Keep native and τ-bench results in separate tables/figures.

8.  Treat τ-bench as validation, not as a replacement for the controlled fault-injection environment.

# 12. Metrics and Logging

| Metric                | Definition                                             |
|-----------------------|--------------------------------------------------------|
| Task success          | Oracle-pass episodes ÷ total episodes                  |
| Failure recovery      | Faulted episodes that oracle-pass ÷ faulted episodes   |
| Error propagation     | Faulted episodes that fail oracle ÷ faulted episodes   |
| Verification overhead | Verification calls ÷ agent actions                     |
| Token/compute cost    | Mean tokens and latency per task/success as configured |
| Reliability-vs-budget | Success rate plotted against verification overhead     |

Report 95% confidence intervals and use paired task/seed comparisons where possible, consistent with the original methodology.

> {  
> "task_id":"p017","policy":"D","model":"MODEL","trial":3,"step":7,  
> "seed":1032,"action":{"tool":"create_purchase_order","args":{}},  
> "true_result":{}, "raw_result":{}, "fault_injected":"wrong_value",  
> "final_result_used":{},"verification_triggered":true,  
> "trigger_reason":"high_risk_tool",  
> "verifier_verdict":{"suspicious":true,"reason":"..."},  
> "recovered":true,"recovery_attempts":1,  
> "latency_ms":842,"tokens_used":311  
> }

# 13. Updated GitHub Structure

> costAware/  
> ├── README.md  
> ├── .gitignore  
> ├── src/  
> │ ├── environment/  
> │ │ ├── state.py  
> │ │ ├── entities.py  
> │ │ ├── tools.py  
> │ │ └── simulator.py  
> │ ├── agent/  
> │ │ ├── graph.py  
> │ │ ├── state.py  
> │ │ └── prompts.py  
> │ ├── verifier/  
> │ │ ├── verifier.py  
> │ │ └── recovery.py  
> │ ├── policies/policies.py  
> │ ├── faults/  
> │ │ ├── injector.py  
> │ │ └── tests/  
> │ ├── evaluation/  
> │ │ ├── oracle.py  
> │ │ ├── metrics.py  
> │ │ └── analysis.py  
> │ └── tau_adapter/README.md  
> ├── tasks/tasks.jsonl  
> ├── experiments/configs/  
> ├── experiments/run_experiment.py  
> ├── logs/  
> ├── results/  
> └── docs/

# 14. Practical Timeline

| Weeks | Milestone               | Visible evidence                    |
|-------|-------------------------|-------------------------------------|
| 1     | Freeze environment      | Spec + tool table + architecture    |
| 2–3   | Simulator               | Runnable procurement world          |
| 4     | Tasks + oracle          | 20 validated tasks + PASS/FAIL      |
| 5–6   | Fault injector          | Fault tests + deterministic replay  |
| 7–8   | LangGraph agent         | Clean tasks end-to-end              |
| 9     | Verifier + recovery     | Fault → verify → recover demo       |
| 10–11 | Policies A–D            | Same task/seed under all policies   |
| 12    | Harness/logging         | One-command batch run               |
| 13–14 | First experiment        | Reliability-vs-overhead graph       |
| 15–16 | Scale                   | Stable baseline grid                |
| 17    | Ablations               | D signal ablation + matched random  |
| 18    | τ-bench pilot           | Adapter feasibility + small run     |
| 19    | Failure/statistics      | Final tables + taxonomy             |
| 20    | Reproduction/paper/demo | Clean rerun + report + presentation |

# 15. Real Progress Checkpoints

9.  A deterministic procurement task passes the oracle without an LLM.

10. A seeded fault reproduces the same corrupted observation.

11. LangGraph agent completes clean tasks.

12. Verifier detects injected faults.

13. Recovery fixes controlled examples.

14. Policies A–D run the same task/seed.

15. Batch runner produces complete logs.

16. First reliability-vs-verification-overhead graph exists.

17. Ablation explains Policy D.

18. τ-bench pilot is either reproducibly integrated or its incompatibility is documented.

19. Final analysis reproduces on a clean setup.

# 16. Risks and Scope Control

| Risk                                     | Control                                                     |
|------------------------------------------|-------------------------------------------------------------|
| Simulator becomes a giant ERP            | Implement only state needed for verification decisions      |
| Tasks become fixed scripts               | Use branching, dependencies, stale/conflicting observations |
| Randomness makes results uninterpretable | Seed faults and match task/seed across policies             |
| Verifier hallucinates                    | Spot-check verdicts against oracle                          |
| LangGraph hides experimental control     | Keep policy/fault/verifier/oracle/logger explicit           |
| τ-bench consumes the project             | Late optional track; never delay native baseline            |
| Too many models/domains                  | Get A–D stable on one environment first                     |
| Under-logging                            | Log every step and preserve run configuration               |

# 17. Final System

> Synthetic Enterprise World  
> ↓  
> LangGraph Agent  
> ↓  
> Tool Action  
> ↓  
> Controlled Fault Injection  
> ↓  
> Policy A/B/C/D  
> ↙ ↘  
> SKIP VERIFY  
> ↓ ↓  
> │ Self-Verifier  
> │ ↓  
> │ OK / SUSPICIOUS  
> │ ↓  
> │ Recovery  
> └───────→ Next Agent Step  
> ↓  
> True Final State  
> ↓  
> Deterministic Oracle  
> ↓  
> PASS / FAIL  
> ↓  
> Logs + Experiments  
> ↓  
> Reliability vs Verification Budget

## Bottom line

The custom procurement simulator is the core research environment. LangGraph is the orchestration framework. Fault injection creates controlled imperfections. The self-verifier provides the extra LLM check. Policies A–D determine when that check is spent. The deterministic oracle provides ground truth. τ-bench is an optional external validation track, not a replacement for the custom environment.

**Build evidence at every phase — not formal milestones.**

# 18. Cost & Performance Optimizations (Advanced Additions)

These are drop-in additions to the existing pipeline (Sections 6–8, 12). They do not change the research question, the oracle, or the fault taxonomy, and they do not add new phases — they reduce how many paid LLM calls the experiment makes per step, and they give the team one extra, genuinely useful research variable (Policy E). Add them opportunistically once the Section 10 baseline is working; none are prerequisites for Phases 0–8.

## Seven additions

- **Two-tier verification cascade.** Run the existing deterministic schema/sanity check first (Sections 4 and 7). Only if that fails, or the risk score is borderline, call a small/cheap model as a tier-1 verifier; escalate to the larger verifier model only when the cheap pass itself says “suspicious” or is low-confidence. Most steps never reach the expensive model.

- **Verdict cache (memoize by state hash).** The simulator is deterministic and seeded, and the plan already repeats the same task/seed across 3–5 trials, four policies, and later ablations (Sections 9–10). Hash (tool, canonicalized args, observed result) and cache the verifier verdict; a repeated faulty observation reuses the cached verdict instead of paying for another call. Log a cache_hit flag so cache use is auditable, not hidden.

- **Confidence from logprobs, not a second call.** model_confidence(action) in Section 7 should read the log-probability / token-entropy of the agent's own action call, not issue a separate LLM request just to ask “was the model sure?” This removes a whole category of extra calls.

- **Policy E — budget-controlled adaptive threshold.** Replace the fixed boolean rules in should_verify with a continuous risk score (weighted sum of: high-risk tool, schema-fail flag, confidence, per-tool historical fault rate from the logs). A small online controller (EWMA or PID-style) nudges the trigger threshold up or down each batch so the realized verification rate tracks a target budget (e.g. 25%) even as task difficulty drifts. This is a genuine fifth policy to report next to A–D, not just an implementation detail — it answers “can the agent hit a reliability target at a known cost?”

- **Batch verifier calls.** When two or more medium/low-risk actions are pending verification in the same step or parallel branch, send them as one LLM call with several JSON items instead of one call each. Cuts the fixed system-prompt token overhead per verification.

- **Prompt caching + a live cost guard.** Mark the long, static verifier system prompt and tool schema for provider-side prompt caching so only the small per-step delta is billed fresh each call. Add a running token/\$ counter to the harness (Section 12) that pauses a batch run if projected spend crosses a configured cap — protects against a runaway overnight sweep.

- **Risk-tiered recovery cap.** Cap recovery attempts (Section 8) by the risk tier of the action instead of one fixed constant for everything: one retry for low/medium-risk suspicious verdicts, up to two for high-risk state-changing ones, then log-and-continue. Avoids spending extra calls on recovery loops that rarely resolve.

## What each addition saves, and when to add it

| **Addition**                | **Mainly cuts**                        | **Add after**                 |
|-----------------------------|----------------------------------------|-------------------------------|
| Two-tier cascade            | Large-model verifier calls             | Phase 6 (Policies A–D)        |
| Verdict cache               | Repeated calls across trials/ablations | Phase 8 (first experiment)    |
| Logprob confidence          | A whole call type                      | Phase 6                       |
| Policy E                    | Verification calls, at a chosen budget | Phase 10 (after D is stable)  |
| Batched verifier calls      | Per-call token overhead                | Phase 7 (harness)             |
| Prompt caching + cost guard | Billed tokens per call                 | Phase 7                       |
| Tiered recovery cap         | Wasted recovery calls                  | Phase 5 (verifier + recovery) |

## Updated should_verify (adds cache + risk score)

```python
def should_verify(action, result, history, step):
    if not passes_schema_check(action["tool"], result):
        return True, "schema_fail"
    key = state_hash(action, result)
    if cache.has(key):
        return cache.get(key)                 # skip a paid call entirely
    score = risk_score(action, result, history)  # tool tier + logprob confidence
                                                   # + per-tool historical fault rate
    decision = (score >= threshold, "risk_score")
    cache.set(key, decision)
    return decision

# threshold is fixed for Policies C/D.
# Policy E only: threshold += k * (actual_verification_rate - target_rate)
```

## Metrics table additions (Section 12)

| **Metric**                            | **Definition**                                                     |
|---------------------------------------|--------------------------------------------------------------------|
| Cache hit rate                        | Verdicts served from cache ÷ total verification decisions          |
| Tier-1 resolution rate                | Cases resolved by the cheap model ÷ cases sent to any LLM verifier |
| Cost per experiment                   | Total tokens and \$ for a full policy × task × trial run           |
| Budget tracking error (Policy E only) | \|actual verification rate − target rate\| over a run              |

None of these change the oracle, the fault taxonomy, or what counts as PASS/FAIL — they only change how cheaply and quickly the system reaches a verification decision, so the existing Phase 0–13 exit criteria and the Section 16 risk controls still apply unchanged.

# 19. Reference Implementation (Section 18 additions)

Concrete, minimal code for the seven Section 18 additions, in build order. None of these require changing the oracle, fault taxonomy, or existing policy logic — they wrap the existing verifier/recovery calls.

## 19.1 Verdict cache — build first (Phase 5, before Policies A–D)

```python
import hashlib, json, sqlite3

class VerdictCache:
    def __init__(self, path="verdict_cache.db"):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, verdict TEXT)")

    def _key(self, tool, args, observed_result):
        blob = json.dumps({"tool": tool, "args": args, "obs": observed_result}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, tool, args, observed_result):
        k = self._key(tool, args, observed_result)
        row = self.db.execute("SELECT verdict FROM cache WHERE key=?", (k,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, tool, args, observed_result, verdict):
        k = self._key(tool, args, observed_result)
        self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (k, json.dumps(verdict)))
        self.db.commit()
```

Wired into the verifier node:

```python
def run_verifier(action, result):
    cached = verdict_cache.get(action["tool"], action["args"], result)
    if cached is not None:
        log_event(cache_hit=True)
        return cached
    verdict = call_llm_verifier(action, result)   # existing self-verifier call
    verdict_cache.set(action["tool"], action["args"], result, verdict)
    log_event(cache_hit=False)
    return verdict
```

## 19.2 Risk-tiered recovery cap (Phase 5)

```python
RECOVERY_LIMITS = {"low": 1, "medium": 1, "high": 2}

def recover(action, verdict, attempts_so_far):
    risk = risk_tier(action["tool"])   # existing HIGH_RISK_TOOLS classification
    return attempts_so_far < RECOVERY_LIMITS[risk]
```

## 19.3 Two-tier verification cascade (Phase 6)

```python
def should_call_expensive_verifier(action, result):
    if not passes_schema_check(action["tool"], result):
        return True   # already suspicious, skip straight to the real verifier

    cheap_verdict = call_llm(model="claude-haiku-4-5", prompt=verifier_prompt(action, result))
    return cheap_verdict["suspicious"] or cheap_verdict["confidence"] < 0.6

def run_verifier(action, result):
    if not should_call_expensive_verifier(action, result):
        return {"suspicious": False, "reason": "resolved_by_tier1"}
    return call_llm(model="claude-sonnet-4-6", prompt=verifier_prompt(action, result))
```

## 19.4 Confidence from logprobs (Phase 6)

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    messages=[...],
    # request logprobs if the provider/SDK supports it for the action-generation call
)
# lower avg logprob / higher entropy on the tool-selection tokens = lower confidence
confidence = estimate_confidence_from_logprobs(response)
```

Fallback if logprobs aren't exposed cleanly: have the agent self-report a confidence field as part of the action JSON it already returns — no extra call needed.

## 19.5 Batched verifier calls + prompt caching + cost guard (Phase 7)

```python
def batch_verify(pending_actions):
    prompt = build_batch_prompt(pending_actions)  # one prompt, N items
    response = call_llm(model="claude-sonnet-4-6", prompt=prompt)
    return parse_batch_verdicts(response)  # list of verdicts, same order
```

```python
messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": VERIFIER_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": per_step_details}
    ]
}]
```

```python
class CostGuard:
    def __init__(self, cap_usd):
        self.spent = 0.0
        self.cap = cap_usd

    def add(self, tokens_in, tokens_out, rate_in, rate_out):
        self.spent += tokens_in * rate_in + tokens_out * rate_out
        if self.spent > self.cap:
            raise RuntimeError(f"Cost cap hit: ${self.spent:.2f} > ${self.cap}")
```

## 19.6 Policy E controller — build last (Phase 10, after A–D are stable)

```python
class BudgetController:
    def __init__(self, target_rate=0.25, k=0.05, threshold=0.5):
        self.target_rate = target_rate
        self.k = k
        self.threshold = threshold
        self.ewma_rate = target_rate

    def update(self, verified_this_batch, total_this_batch):
        actual_rate = verified_this_batch / max(total_this_batch, 1)
        self.ewma_rate = 0.8 * self.ewma_rate + 0.2 * actual_rate
        self.threshold += self.k * (self.ewma_rate - self.target_rate)
        self.threshold = min(max(self.threshold, 0.0), 1.0)

def should_verify_policy_e(action, result, history, controller):
    score = risk_score(action, result, history)  # tool tier + confidence + historical fault rate
    return score >= controller.threshold
```

Call `controller.update(...)` after each batch so the threshold drifts toward the target verification rate.

## 19.7 Build order for a 3-person team

| Order | Build | Time | Why now |
|---|---|---|---|
| 1 | Verdict cache | ~half day | Zero risk, immediate savings, no dependencies |
| 2 | Tiered recovery cap | ~1 hour | Trivial change to existing recovery loop |
| 3 | Two-tier cascade | ~1 day | Biggest single cost cut, needed before Phase 8 |
| 4 | Logprob / self-reported confidence | ~half day | Removes a whole call type |
| 5 | Prompt caching + cost guard | ~half day | Cheap insurance before the first real experiment |
| 6 | Batching | ~1 day | Nice-to-have, do if time allows before Phase 7 |
| 7 | Policy E | ~2 days | Only after the A–D baseline is solid and reproducible |
