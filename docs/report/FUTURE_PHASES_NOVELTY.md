# CostAware — Novelty Check for Future Phases (5–13)

**Date:** 14 October 2026
**For:** CostAware team
**Basis:** Literature search of arXiv / NeurIPS / ICML / TMLR up to 14 Oct 2026 (mostly abstracts — see caveats at the end).

---

## TL;DR

- **If we follow the plan exactly as written, we will hit novelty issues.** The headline result the plan aims for — *"adaptive Policy D approaches verify-always reliability at lower cost"* (H3) — has already been published by several 2026 papers.
- **Phases 1–4 alone are not publishable as a novel paper.** They are infrastructure (simulator, tasks, oracle, fault injector, agent). There are already 7+ fault-injection benchmarks for tool-using agents in 2026, and we have no LLM results yet.
- **The phases are still worth building — we just need to change what the paper claims.** Stop presenting Policy D as "the solution". Make the paper answer: **"Which cheap verification signals catch which kinds of tool faults, and at what cost?"**

---

## What is still ours (not found in any published work)

1. **Matched faults across verification policies.** Faults are keyed by `SHA-256(seed | tool | args | occurrence)`, so the same agent action gets the same fault under every policy, even though some policies make extra verification calls. Prior benchmarks compare *models/agents*; nobody compares *verification policies* under identical faults.
2. **Per-fault-type coverage of verification signals.** Our LLM-free analysis (`scripts/trigger_coverage.py`, 20 tasks × 50 seeds = 6,950 tool calls, fault rate 0.25) already shows:

   | | Verify rate | Catches faulted steps |
   |---|---|---|
   | Policy C (every 3rd step) | 38.1% | 39.8% |
   | Policy D (adaptive) | 43.7% | 63.1% |

   D looks better overall, **but**:
   - D's content-based trigger (schema check) catches **0%** of *silent* faults (wrong value, stale info, incorrect status, corrupted observation — results that look valid but are wrong).
   - On silent faults, D is **no better than every-3rd-step** (42.1% vs 44.4%).
   - On `wrong_value` (31% vs 47%) and `corrupted_obs` (18% vs 48%), D is **worse** — these faults land on low-risk read tools (`check_budget`, `get_quotes`) that D never checks.
   - Same pattern at fault rates 0.10 and 0.40.

---

## Phase-by-phase novelty risk

| Phase | What it adds | Novelty risk if claimed as new | Already done by |
|---|---|---|---|
| **5. Verifier + recovery** | LLM self-verifier, re-call, re-plan | **HIGH** | CRITIC, Reflexion; ToolMaze, Outcome Monitors (recovery). Self-verification known to be unreliable (Huang et al., ICLR'24) |
| **6. Policies A–D** | never / always / every-3rd / adaptive | **HIGH for D** | Risk-tier & schema triggers: Reason Less Verify More, write-triggered reconsideration, SIEVE, SafeHarness. A/B/C are standard baselines — fine |
| **7. Harness + logging** | batch runner | Not a contribution | Engineering |
| **8. First experiment** | "adaptive ≈ always, cheaper" | **HIGH** | SAG (NeurIPS'26), Sherlock, Reason Less Verify More |
| **9. Scale** | more tasks / models / seeds | Not a contribution | Makes results stronger, not newer |
| **10. Ablations + matched random** | which signal helps, on which faults | **LOW — this is where our paper lives** | Nobody found doing per-fault-type signal analysis with matched faults |
| **11–12. τ-bench pilot** | external validity | MEDIUM | τ/τ²-bench used by Reason Less, Verifier Tax, SSCBench, Reconsider. Reason Less found rule-gates help little on τ-bench retail. Adds credibility, not novelty |
| **13. Stats + paper** | CIs, paired tests | Not a contribution | Good practice — keep |

### Section 18 add-ons (from the implementation plan)

| Add-on | Risk | Why |
|---|---|---|
| Two-tier cascade (Haiku → Sonnet) | **HIGH** | FrugalGPT, SIEVE, SafeHarness, OMVV |
| Logprob confidence as a trigger | **HIGH as a method** | SAG already gates on entropy. **LOW** if we instead *test whether it misses silent faults* — that is new |
| Verdict cache, batching, prompt caching, cost guard | Engineering | Use them; don't claim them |
| Tiered recovery cap | Minor | Too small to be a contribution |
| **Policy E (EWMA target-rate controller)** | LOW–MEDIUM | No exact match found. Closest: AVA (budgets), Conformal Selective Acting (fixed verify rate), OMVV. A plain controller alone looks thin; and if its risk score uses the same blind signals, it inherits the silent-fault blind spot |

---

## Revised hypotheses (proposal)

| Original | Status | Revised |
|---|---|---|
| H1: no verification degrades with horizon/faults | OK (expected) | Keep as supporting result |
| H2: verify-always is most expensive | OK (expected) | Keep as supporting result |
| H3: D ≈ B at lower cost | **Already published** | **D's advantage comes only from loud faults (errors, timeouts); on silent faults it is no better than a fixed schedule.** Our data already points this way |
| H4: which signals matter | Keep — this is the core | Break down **per fault type**, and add **model uncertainty** as a third signal |
| — | New | **H5:** Model uncertainty (the signal SAG uses) is also blind to silent faults — a corrupted-but-plausible observation (e.g., a stale quote that looks valid) may make the agent *more* confident, not less |
| — | New | **H6:** A target-rate controller (Policy E) keeps silent-fault coverage only if it includes a content-sensitive signal |

### Proposed paper claim

> **"Cheap verification signals are blind to silent tool faults."**
> The three cheap signals used in current systems — tool risk tier, output-format checks, and model uncertainty — each fail on in-format wrong values. Shown with matched faults so every policy is compared on identical faults.

---

## What this means for each phase going forward

- **Phase 5–6:** build as planned, but describe Policy D as *the baseline being analysed*, not the proposed method.
- **Phase 4 / 6:** wire up a real confidence signal. Claude's API does **not** return logprobs → we need an open model (local, e.g. via vLLM/Ollama) or an API that exposes logprobs. **Team decision needed.**
- **Phase 8:** report results **split by fault type** (silent vs loud), not just overall success.
- **Phase 10:** this is the main result — signal × fault-type table + rate-matched random control.
- **Policy E:** only claim it if we add a content-sensitive signal; otherwise keep it as an appendix.
- **τ-bench:** optional; don't let it delay Phase 10.

### Fastest route to a first paper

Phases 1–4 (done) + **one real-LLM experiment**: run the agent on the 20 tasks clean and with matched faults, record the model's uncertainty at every step, compare faulted vs clean steps. No verifier needed. That plus the existing trigger-coverage analysis is a solid workshop / IEEE conference paper. Adding Phases 5–6 later turns it into a full paper.

---

## Things in our own docs reviewers would flag

- The plan calls Policy D the "proposed method" — needs reframing.
- Policy D's low-confidence trigger never fires: the code reads a `_confidence` field that no tool or model provides.
- The plan says faults use `random.Random(seed)`; the code uses SHA-256-keyed faults (better — update the plan to match).
- 2 of 173 tests fail (`tests/test_agent.py`, langgraph recursion-limit error).
- The real LLM agent run on clean tasks ("Phase 4 visible progress") has not been done yet.
- Fault mix is uneven (malformed / missing field / timeout appear more often than the others).

---

## Caveats

1. **Novelty can change before we submit.** Three closely related papers appeared on 5, 7 and 8 October 2026 alone. Re-run the literature search right before submission. If someone publishes a "signal × fault-type" analysis first, the matched-fault methodology is our fallback contribution.
2. This check is mostly based on **abstracts**. Someone should read the full text of **SAG**, **Sherlock**, and **Reason Less, Verify More** — those are the papers reviewers will compare us to.
3. Full list of overlapping work with arXiv IDs: `docs/report/NOVELTY_AUDIT.md`. Paper draft: `docs/report/costaware_ieee.tex`.

---

## Key references

| Paper | Link | Why it matters to us |
|---|---|---|
| SAG — Selective Critique for Cost-Aware LLM Agents (NeurIPS'26) | https://arxiv.org/abs/2610.07335 | Closest work: uncertainty-gated critique, never/always baselines |
| Sherlock | https://arxiv.org/abs/2511.00330 | Verifies only error-prone steps |
| Reason Less, Verify More | https://arxiv.org/abs/2607.07405 | Deterministic gates before writes, τ²-bench |
| Loud Failures, Quiet Failures | https://arxiv.org/abs/2610.10062 | Agents miss in-format wrong values |
| Outcome Monitors | https://arxiv.org/abs/2608.19303 | Detecting silent tool failures |
| AgentCheck | https://arxiv.org/html/2607.11098 | Silent data-quality faults are agents' weakest category |
| Look Before You Leap | https://arxiv.org/abs/2609.11957 | Pre-action verification, silent failures |
| Write-triggered reconsideration | https://arxiv.org/abs/2607.01426 | Re-check before backend writes |
| PlanFence | https://arxiv.org/pdf/2609.03340 | Re-validate a write's inputs before commit |
| ReliabilityBench | https://arxiv.org/abs/2601.06112 | Fault-injection benchmark |
| AgentNoiseBench (ICML'26) | https://arxiv.org/html/2602.11348v1 | Fault-injection benchmark |
| AgentChaos (ASE'26) | https://arxiv.org/html/2608.06790v1 | Fault-injection benchmark |
| ToolMaze | https://arxiv.org/abs/2606.05806 | Tool failures + recovery cost |
| SSCBench | https://arxiv.org/abs/2610.11514 | Validity of fault-injection tests |
| Verified Tool Calls | https://arxiv.org/abs/2608.02645 | Timeout-after-write duplicates |
| AVA (TMLR'26) | https://mlanthology.org/tmlr/2026/patel2026tmlr-anytime/ | Budgeted verification cascades |
