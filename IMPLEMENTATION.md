# 📘 Tech Stack & System Implementation
### Cost-Aware Adaptive Verification for Long-Horizon LLM Agents
> Extracted & structured from `Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md`

---

## 🧱 Tech Stack (Exactly as Specified)

| Layer | Technology | Source in Plan |
|---|---|---|
| **Agent Orchestration** | **LangGraph** | Section 6: *"team has chosen LangGraph"* |
| **LLM (Agent)** | Any LLM (model-agnostic) | Section 8, 12 — *"1 model × 4 policies"* |
| **LLM (Verifier Tier 1)** | `claude-haiku-4-5` | Section 19.3 |
| **LLM (Verifier Tier 2)** | `claude-sonnet-4-6` | Section 19.3 |
| **Environment** | Custom Python Simulator | Section 2 — *Synthetic Enterprise Procurement* |
| **Fault Injection** | `random.Random(seed)` — seeded Python | Section 5 |
| **Oracle** | Pure Python (NO LLM) | Section 4 — *"oracle must never be an LLM"* |
| **Verdict Cache** | SQLite | Section 19.1 |
| **State Schema** | Python dataclasses / dicts | Section 6 |
| **Logging** | JSONL files | Section 12 |
| **Config** | Experiment config files | Section 7 (Phase 7) |
| **Testing** | Unit tests (Pytest implied) | Sections 3, 5 — *"unit-tested before agent is trusted"* |
| **Optional Benchmark** | τ-bench | Section 11 |

---

## 🌍 Environment — Synthetic Procurement World

The plan defines **9 entities** that make up the simulated world:

```
Vendor          → id, eligibility, approval/suspension, preferred, payment profile
Component       → id, category, reference price, required quantity, availability
Supplier Quote  → vendor, component, unit_price, quantity, expiry, shipping, status
Project         → id, owner, procurement_rules, priority
Budget          → allocated, spent, reserved, remaining
Purchase Order  → id, vendor, items, total, status, approval, release_state
Approval        → level, requester, approver, status, validity_after_changes
Invoice         → id, PO, amount, line_items, mismatch/status
Shipment        → id, PO, quantity, destination, dispatch_status
```

The simulator maintains **two parallel views**:

```
TRUE STATE  (only oracle sees this)
─────────────────────────────────
Vendor C: approved=False, suspended=True
Budget:   remaining=35000
PO:       status=NOT_CREATED

FAULTY OBSERVATION  (what agent sees after fault injection)
───────────────────────────────────────────────────────────
Vendor C: approved=True, suspended=False   ← LIE
Budget:   remaining=40000                  ← WRONG VALUE
```

---

## 🔧 Tool Set (16 Tools with Risk Tiers)

```
🟢 LOW RISK (Read-only)          🟡 MEDIUM RISK (Write)       🔴 HIGH RISK (State-changing)
─────────────────────────        ─────────────────────        ─────────────────────────────
search_vendors()                 request_discount()           create_purchase_order()
get_vendor_details()             request_approval()           modify_order()
check_vendor_status()                                         approve_order()
get_quotes()                                                  release_order()
check_quote_validity()                                        cancel_order()
check_budget()
check_existing_orders()
compare_quotes()
check_invoice()
```

> ⚠️ The plan explicitly states: *"The high-risk tag is an actual Policy D signal, not just documentation."*

---

## ⚙️ LangGraph Architecture (Section 6)

```
START
  │
  ▼
[Initialize Task/State]
  │   ← task_id, goal, history, step count
  ▼
[Agent Decision Node]
  │   ← Claude picks next tool from the 16-tool set
  ▼
[Tool Execution Node]
  │   ← calls simulator tool
  ▼
[Fault Injection Node]
  │   ← random.Random(seed) decides if/what to corrupt
  ▼
[Policy Router Node]   ← THE CORE EXPERIMENTAL VARIABLE
  │
  ├── SKIP ─────────────────────────────────────┐
  │                                             │
  └── VERIFY                                   │
        │                                       │
        ▼                                       │
  [Self-Verifier Node]  (extra LLM call)        │
        │                                       │
        ├── OK ──────────────────────────────── ┤
        │                                       │
        └── SUSPICIOUS                          │
              │                                 │
              ▼                                 │
        [Recovery Node] ─────────────────────── ┘
              │
              ▼
[Update State] → Continue / DONE
              │
              ▼
[Deterministic Oracle] → PASS / FAIL
              │
              ▼
[JSONL Logger]
```

### LangGraph State Object

Every node reads and writes this shared state:

```python
class AgentState:
    task_id:             str
    goal:                str
    observations:        list    # agent-visible history (may be corrupted)
    latest_action:       dict    # {"tool": "create_purchase_order", "args": {...}}
    latest_result:       dict    # what tool returned (may be faulted)
    verify_decision:     bool
    trigger_reason:      str     # "high_risk_tool" | "schema_fail" | "low_confidence"
    verifier_verdict:    dict    # {"suspicious": bool, "reason": str}
    recovery_attempts:   int
    step:                int
    max_steps:           int
    # Research metadata (hidden from agent, used by oracle/logger)
    true_result:         dict
    fault_injected:      str
    oracle_pass:         bool
```

---

## 🎯 Policies A–D (Section 7) — The Experimental Variable

```python
def should_verify(action, result, history, step):

    # Policy A — Never verify (lower-bound baseline)
    return False

    # Policy B — Always verify (high-reliability, high-cost reference)
    return True

    # Policy C — Fixed schedule every N=3 steps
    return step % 3 == 0

    # Policy D — Adaptive (PROPOSED METHOD)
    if action["tool"] in HIGH_RISK_TOOLS:               # create_PO, approve, release, cancel
        return True
    if not passes_schema_check(action["tool"], result):  # malformed/missing field
        return True
    if model_confidence(action) < CONF_THRESHOLD:        # low-confidence action
        return True
    return False
```

| Policy | Rule | Purpose |
|---|---|---|
| **A — No Verification** | Never verify | Lower-bound baseline |
| **B — Verify Every Step** | Verify after every action | High-reliability / high-cost reference |
| **C — Fixed Schedule** | Verify every N=3 steps | Fixed-cost baseline |
| **D — Adaptive** | High-risk OR schema fail OR low confidence | **Proposed method** |

---

## 🐛 Fault Injector (Section 5) — 8 Fault Types

```python
# Uses: random.Random(seed)  ← fully reproducible!

FAULT_TYPES = {
    "wrong_value":       # Budget true=35k → reports 40k
    "stale_info":        # Expired quote → appears active
    "contradictory":     # Vendor suspended → profile says approved
    "malformed_output":  # Quote object has wrong type/structure
    "missing_field":     # Approval object has no 'status' field
    "timeout":           # Tool returns nothing / times out
    "incorrect_status":  # PO pending → tool says approved
    "corrupted_obs":     # Reserved budget 10k → reports 0
}

# Rules from the plan:
# → Log: true_result, observed_result, fault_type  (every step)
# → Do NOT mutate hidden ground truth
# → Match task+seed across all 4 policies
# → Start at fault_rate = 0.25
# → Optional sweep: 0.10 / 0.25 / 0.40
```

| Fault | Example | Agent-visible Effect |
|---|---|---|
| Wrong value | Budget true = 35k | Reports 40k |
| Stale information | Quote expired | Old quote appears active |
| Contradictory | Vendor suspended | Profile says approved, status says suspended |
| Malformed output | Quote object invalid | Wrong type/missing structure |
| Missing field | Approval lacks status | Required field omitted |
| Timeout | Quote service delayed | Timeout/no result |
| Incorrect status | PO pending approval | Tool says approved |
| Corrupted observation | Reserved budget = 10k | Reports 0 |

---

## 🔍 Self-Verifier + Recovery (Section 8)

```python
# Verifier output format
response = {
    "suspicious": True,
    "reason": "Vendor status conflicts with previous vendor info"
}

# Recovery protocol (3 attempts max)
# attempt_1 → Re-call the SAME tool once
# attempt_2 → If still suspicious: re-plan with flagged concern
# attempt_3 → Log "unrecovered_fault" — do NOT force success
```

---

## 🚀 7 Advanced Cost Optimizations (Sections 18 & 19)

> Drop-in additions — add **only after Phase 8 baseline works**. None change the oracle or fault taxonomy.

| # | Optimization | What It Saves | Add After |
|---|---|---|---|
| 1 | **Verdict Cache** (SQLite + SHA256) | Repeated LLM calls across trials/ablations | Phase 5 |
| 2 | **Tiered Recovery Cap** (low=1, high=2) | Wasted recovery loops | Phase 5 |
| 3 | **Two-Tier Cascade** (Haiku → Sonnet) | Expensive verifier calls | Phase 6 |
| 4 | **Logprob Confidence** (token entropy) | Eliminates a whole call type | Phase 6 |
| 5 | **Prompt Caching + Cost Guard** ($cap) | Billed tokens + runaway cost | Phase 7 |
| 6 | **Batched Verifier Calls** (N→1 call) | Per-call system prompt overhead | Phase 7 |
| 7 | **Policy E Controller** (EWMA threshold) | Hits a target verification % (e.g. 25%) | Phase 10 |

### Verdict Cache — SQLite

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

### Two-Tier Cascade — Cheap → Expensive

```python
def should_call_expensive_verifier(action, result):
    if not passes_schema_check(action["tool"], result):
        return True   # already suspicious, skip straight to expensive

    cheap_verdict = call_llm(model="claude-haiku-4-5", prompt=verifier_prompt(action, result))
    return cheap_verdict["suspicious"] or cheap_verdict["confidence"] < 0.6

def run_verifier(action, result):
    if not should_call_expensive_verifier(action, result):
        return {"suspicious": False, "reason": "resolved_by_tier1"}
    return call_llm(model="claude-sonnet-4-6", prompt=verifier_prompt(action, result))
```

### Policy E — Budget-Controlled Controller (EWMA)

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
    score = risk_score(action, result, history)
    return score >= controller.threshold
```

### Updated `should_verify` (Adds Cache + Risk Score)

```python
def should_verify(action, result, history, step):
    if not passes_schema_check(action["tool"], result):
        return True, "schema_fail"
    key = state_hash(action, result)
    if cache.has(key):
        return cache.get(key)                    # skip a paid call entirely
    score = risk_score(action, result, history)  # tool tier + logprob confidence
                                                 # + per-tool historical fault rate
    decision = (score >= threshold, "risk_score")
    cache.set(key, decision)
    return decision

# threshold is fixed for Policies C/D
# Policy E only: threshold += k * (actual_verification_rate - target_rate)
```

### Cost Guard

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

---

## 📝 Log Schema — Every Step (Section 12)

```jsonc
{
  "task_id":                "p017",
  "policy":                 "D",
  "model":                  "claude-sonnet-4-6",
  "trial":                  3,
  "step":                   7,
  "seed":                   1032,
  "action":                 {"tool": "create_purchase_order", "args": {}},
  "true_result":            {},
  "raw_result":             {},
  "fault_injected":         "wrong_value",
  "final_result_used":      {},
  "verification_triggered": true,
  "trigger_reason":         "high_risk_tool",
  "verifier_verdict":       {"suspicious": true, "reason": "..."},
  "recovered":              true,
  "recovery_attempts":      1,
  "latency_ms":             842,
  "tokens_used":            311
}
```

---

## 📊 Metrics (Section 12)

| Metric | Formula |
|---|---|
| **Task Success Rate** | oracle_pass episodes / total episodes |
| **Failure Recovery Rate** | faulted episodes that pass / faulted episodes |
| **Error Propagation** | faulted episodes that fail / faulted episodes |
| **Verification Overhead** | verify calls / total agent actions |
| **Token / Cost** | mean tokens + latency per task |
| **Reliability-vs-Budget** | success rate plotted against verification overhead |
| **Cache Hit Rate** | verdicts from cache / total verify decisions |
| **Tier-1 Resolution** | resolved by Haiku / sent to any LLM verifier |
| **Cost per Experiment** | total tokens + $ for full policy x task x trial run |
| **Budget Tracking Error** | actual verification rate - target rate (Policy E only) |

---

## 📅 13-Phase Timeline (Section 10)

| Phase | Goal | Visible Evidence | Exit Criterion |
|---|---|---|---|
| **0** | Freeze design | Spec + tool table + architecture | No unresolved core decisions |
| **1** | Build Python simulator | Runnable procurement world | 10 tasks execute correctly |
| **2** | Write 20 tasks + oracle | 20 validated tasks + PASS/FAIL | Oracle never depends on LLM |
| **3** | Fault injector + replay | Same seed = same fault | All core fault types pass tests |
| **4** | LangGraph agent (clean) | Agent completes clean tasks | No infinite loops; DONE works |
| **5** | Self-verifier + recovery | Fault → verify → recover demo | Recovery identical across policies |
| **6** | Policies A–D | Same task/seed under all 4 | Only verification timing changes |
| **7** | Logging + harness | One-command batch run | No manual spreadsheet copying |
| **8** | First real experiment | Reliability-vs-overhead graph | Full run: config → plot |
| **9** | Scale | Stable baseline grid | Reproducible baseline grid |
| **10** | Ablations on Policy D | D signal ablation + matched random | Same tasks/seeds/faults across variants |
| **11** | τ-bench pilot (optional) | Adapter feasibility + small run | Do not delay native baseline |
| **12** | Native vs τ-bench | Two-track evaluation table | No invalid metric mixing |
| **13** | Stats + paper | Final paper + reproduction guide | Clean-machine reproduction succeeds |

### Week-by-Week Schedule

| Weeks | Milestone | Visible Evidence |
|---|---|---|
| 1 | Freeze environment | Spec + tool table + architecture |
| 2–3 | Simulator | Runnable procurement world |
| 4 | Tasks + oracle | 20 validated tasks + PASS/FAIL |
| 5–6 | Fault injector | Fault tests + deterministic replay |
| 7–8 | LangGraph agent | Clean tasks end-to-end |
| 9 | Verifier + recovery | Fault → verify → recover demo |
| 10–11 | Policies A–D | Same task/seed under all policies |
| 12 | Harness/logging | One-command batch run |
| 13–14 | First experiment | Reliability-vs-overhead graph |
| 15–16 | Scale | Stable baseline grid |
| 17 | Ablations | D signal ablation + matched random |
| 18 | τ-bench pilot | Adapter feasibility + small run |
| 19 | Failure/statistics | Final tables + taxonomy |
| 20 | Reproduction/paper/demo | Clean rerun + report + presentation |

---

## 📁 Final Repo Structure (Section 13)

```
costAware/
├── src/
│   ├── environment/
│   │   ├── state.py          ← simulator true state
│   │   ├── entities.py       ← Vendor, PO, Budget, Invoice, etc.
│   │   ├── tools.py          ← all 16 tools
│   │   └── simulator.py      ← reset, init, state transitions
│   ├── agent/
│   │   ├── graph.py          ← LangGraph StateGraph definition
│   │   ├── state.py          ← AgentState schema
│   │   └── prompts.py        ← system + task prompts
│   ├── verifier/
│   │   ├── verifier.py       ← 2-tier LLM verifier
│   │   └── recovery.py       ← recovery logic + tiered retry cap
│   ├── policies/
│   │   └── policies.py       ← Policy A/B/C/D/E logic
│   ├── faults/
│   │   ├── injector.py       ← seeded fault wrapper
│   │   └── tests/            ← unit tests for all fault types
│   ├── evaluation/
│   │   ├── oracle.py         ← deterministic PASS/FAIL (no LLM)
│   │   ├── metrics.py        ← all metric calculations
│   │   └── analysis.py       ← plots + tables + CIs
│   └── tau_adapter/
│       └── README.md         ← τ-bench integration notes
├── tasks/
│   └── tasks.jsonl           ← 20 → 50 → 100+ task definitions
├── experiments/
│   ├── configs/              ← Hydra/YAML experiment configs
│   └── run_experiment.py     ← one-command batch runner
├── logs/                     ← per-step JSONL logs (one file per run)
├── results/
│   ├── figures/              ← reliability-vs-overhead plots
│   └── tables/               ← metric tables + ablation results
├── docs/
├── IMPLEMENTATION.md         ← this file
├── Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md
├── README.md
└── .gitignore
```

---

## ⚠️ Risk Register (Section 16)

| Risk | Control |
|---|---|
| Simulator becomes a giant ERP | Implement only state needed for verification decisions |
| Tasks become fixed scripts | Use branching, dependencies, stale/conflicting observations |
| Randomness makes results uninterpretable | Seed faults and match task/seed across policies |
| Verifier hallucinates | Spot-check verdicts against oracle |
| LangGraph hides experimental control | Keep policy/fault/verifier/oracle/logger explicit |
| τ-bench consumes the project | Late optional track; never delay native baseline |
| Too many models/domains | Get A–D stable on one environment first |
| Under-logging | Log every step and preserve run configuration |

---

## ✅ Real Progress Checkpoints

- [ ] A deterministic procurement task passes the oracle without an LLM
- [ ] A seeded fault reproduces the same corrupted observation
- [ ] LangGraph agent completes clean tasks
- [ ] Verifier detects injected faults
- [ ] Recovery fixes controlled examples
- [ ] Policies A–D run the same task/seed identically
- [ ] Batch runner produces complete logs
- [ ] First reliability-vs-verification-overhead graph exists
- [ ] Ablation explains Policy D signal contributions
- [ ] τ-bench pilot is integrated or incompatibility is documented
- [ ] Final analysis reproduces on a clean machine setup

---

## 🔬 Research Hypotheses

| Hypothesis | Claim | How to Verify |
|---|---|---|
| **H1** | No verification becomes more vulnerable as horizon/faults increase | Compare Policy A failure rate vs horizon length |
| **H2** | Verify-every-step improves reliability but has high overhead | Compare Policy B cost vs A across tasks |
| **H3** | Adaptive Policy D approaches B's reliability at lower cost | Plot D vs B on reliability-vs-overhead graph |
| **H4** | High-risk actions and schema failures are valuable triggers | Ablation: D vs D-risk vs D-schema vs D-confidence |

---

*Generated from `Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md`*
*Last updated: 2026-09-23*
