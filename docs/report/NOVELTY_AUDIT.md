# Novelty audit — CostAware (checked 2026-10-14)

Searched arXiv / OpenReview / ICML / TMLR for work overlapping with CostAware. Judgements are
based on **abstracts**; read the full text of every "High" row before submitting.

## Do NOT claim as new (prior work exists — cite it)

| Our component | Prior work | Overlap |
|---|---|---|
| Fault injection into tool outputs, fault taxonomy (timeout, malformed, wrong value, schema drift) | ReliabilityBench [2601.06112], AgentNoiseBench [2602.11348, ICML'26], AgentChaos [2608.06790, ASE'26], ToolMaze [2606.05806], AgentProp-Bench [2604.16706], SSCBench [2610.11514] | High |
| "Agents miss plausible-but-wrong tool values" | Loud Failures, Quiet Failures [2610.10062] (Oct 2026) | High — our Sec. V is the *policy-level* analogue; cite it prominently |
| Selectively invoking a critic/verifier to save tokens, never/always baselines | SAG — Selective Critique for Cost-Aware LLM Agents [2610.07335, NeurIPS'26] | High — closest work; differs: no tool-output faults, ALFWorld-style envs, entropy gate |
| Verifying only error-prone steps; fault-injection-guided placement | Sherlock [2511.00330] | High |
| Verify only before state-changing writes (= Policy D high-risk trigger) | Write-triggered reconsideration [2607.01426]; RACG risk tiers [2606.13884]; MemTX irreversible gate [2607.23929] | High |
| Deterministic check first, LLM judge only on escalation (= schema check + 2-tier verifier) | SIEVE [2512.06716], SafeHarness [2604.13630], Verification as an Architectural Layer [2609.31937] | High |
| Cheap → expensive verifier cascade (Haiku → Sonnet) | FrugalGPT [2305.05176], OMVV [2610.02632], AVA [TMLR'26] | High |
| Timeout-after-write creates duplicates; verify-before-retry | Verified Tool Calls [2608.02645] | Medium |
| Budget-constrained adaptive reliability, Pareto frontier | AVA [TMLR'26], Communication-theoretic framework [2605.09121] | Medium (reasoning tasks, not stateful agents) |
| "Silent / in-format tool failures escape error-triggered checks" (general phenomenon) | AgentCheck [2607.11098], Outcome Monitors [2608.19303], Look Before You Leap [2609.11957], SilentProbe [2609.00035], Tools Fail [2406.19228] | High — the phenomenon is known; only the *policy-level, matched-fault* measurement is ours |
| Deterministic read-only gates before writes recover silent wrong-state failures | Reason Less, Verify More [2607.07405] (τ²-bench, +12.4pp) | High — closest to any "re-check before write" fix |
| Re-validate the reads a write depends on before commit | PlanFence [2609.03340], Agent-Sentry [2603.22868], provenance survey [2606.04990] | High — do not propose this as our method |
| Enterprise / business simulated environment | τ-bench, EnterpriseBench, Vending-Bench, EconAgentBench (procurement) | Medium |

## What is still defensible as a contribution

1. **Matched faults across verification policies** — per-call SHA-256-keyed faults so the same
   action gets the same fault under every policy despite extra verifier calls. Not found in any
   of the above (they compare *models/agents*, not *verification policies*, under fixed faults).
2. **Trigger-coverage finding** (`scripts/trigger_coverage.py`): risk+schema adaptive verification
   fires on 0% of silent faults via content, and is no better than a fixed schedule on them
   (42.1% vs 44.4%), worse on wrong_value / corrupted_obs. Not reported elsewhere.
3. **Simulator that permits policy violations** so misled agents can actually fail, judged by an
   LLM-free oracle — a design point, modest on its own.
4. **Policy E (EWMA controller targeting a verification rate)** — no direct match found, but it is
   not implemented/evaluated yet, so do not claim it.

## Not novel enough alone
Policy D as such (risk tier + schema check) — it is the same idea as several 2026 papers.
Frame it as the *baseline being analysed*, not as the proposed method.

## Plagiarism hygiene
- The paper text was written fresh; no sentences copied from the papers above.
- Entries marked `% VERIFY` in `references.bib` lack a confirmed author list — fix before submission.
- Run the final PDF through your university's similarity checker (Turnitin/iThenticate).
