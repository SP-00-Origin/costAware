# Project Status & Krish's Branch Change Analysis

**Repository:** `SP-00-Origin/costAware`  
**Base Commit (Your Previous State):** `10694f7` (*"phase 1 updated"*)  
**Merged Commit (Krish's Branch HEAD):** `634b479` (*Merge PR #2 from krish01info/main*)  
**Test Suite Status:** **173 passed** (`python -m pytest tests -q` in ~11s)

---

## Executive Summary

Krish's branch advances the project from an early prototype of the simulator (Phase 1 draft) to a **fully functioning, end-to-end research testbed spanning Phases 1 through 4**. 

All core infrastructure required to run agents, inject faults, evaluate deterministic ground-truth outcomes, and log trajectories is now operational. Specifically:
1. **Phase 1 (Simulator & Tool Registry)** is fully formalized with 17 tools, deterministic sequential IDs, quote-driven purchase orders, and state-machine transitions.
2. **Phase 2 (Tasks & Deterministic Oracle)** adds 20 benchmark procurement tasks and a strict, non-LLM ground-truth evaluator.
3. **Phase 3 (Fault Injector & Replay Engine)** fixes critical fault-injection bugs, adds deterministic per-call seed hashing, and enables trajectory replay.
4. **Phase 4 (LangGraph Agent Architecture)** introduces the LangGraph workflow (`init -> agent -> tool_exec -> fault_injection -> policy_router -> observe -> finalize`), CLI runner (`run_agent.py`), trajectory logger, and scripted/Anthropic LLM support.

---

## Current Project Status: Phase Roadmap

| Phase | Description | Status | Evidence / Implementation |
| :--- | :--- | :---: | :--- |
| **Phase 1** | Deterministic Simulator & Tool Registry | **DONE** | 17 tools registered, sequential IDs, state-transition rules, 20 unit tests |
| **Phase 2** | Tasks Dataset & Deterministic Oracle | **DONE** | 20 validated tasks (7 easy, 8 medium, 5 hard) in `tasks/tasks.jsonl`, zero-LLM oracle |
| **Phase 3** | Fault Injector & Replay Engine | **DONE** | 8 fault types, per-call keyed RNG (`sha256`), bit-for-bit replay in `src/faults/replay.py` |
| **Phase 4** | LangGraph Agent Pipeline & Logging | **DONE** | LangGraph state graph in `src/agent/graph.py`, CLI runner, JSONL trajectory logger |
| **Phase 5** | Self-Verification Node & Verdict Cache | *NEXT* | Stubs present in `policy_router`; cache and LLM verifier to be built |
| **Phase 6** | Recovery Mechanism & Risk Cascade | *PENDING* | Recovery attempt limit and two-tier verifier |
| **Phase 7** | Policies A–D Benchmarking & Ablations | *PENDING* | Experiments comparing No-Verify, Verify-All, Random, and Adaptive |
| **Phase 10** | Policy E (Adaptive Budget Controller) | *PENDING* | PID/EWMA dynamic threshold adjuster |

---

## Detailed Breakdown of Krish's Changes

### 1. Phase 1: Environment, Simulator & Tool Registry

#### A. Tool Registry (`src/environment/tools.py`)
* Registered **17 procurement tools** with complete metadata:
  * Risk tiers (`low`, `medium`, `high`) utilized by Policy D.
  * Human-readable descriptions and full JSON argument schemas for LLM tool calling.
* Added `dispute_invoice` tool (medium risk) to handle invoice-mismatch scenarios.

#### B. Architectural Separation: Workflow Rules vs. Policy Constraints
* **Workflow / Referential Integrity (Enforced by Simulator):**
  * Unknown IDs, invalid state transitions, or releasing a PO exceeding `require_approval_above` without a valid approval are rejected with error messages.
* **Policy Mistakes (Allowed by Simulator, Judged by Oracle):**
  * Previously, the simulator blocked actions like ordering from suspended vendors or exceeding budgets. Krish changed this so these actions *go through* to state. This is crucial for research: if the simulator blocks policy mistakes, fault injection would never lead to agent failure, making verification policies (A vs B vs C vs D) indistinguishable.

#### C. Simulator Improvements (`src/environment/simulator.py`)
* **Orders Priced from Quotes:** `create_purchase_order(project_id, quote_id, quantity)` pulls vendor, unit price, and shipping costs directly from existing quotes, preventing hallucinated pricing.
* **Deterministic Sequential IDs:** Replaced randomized `uuid4()` with reproducible IDs (`PO-0001`, `APR-0001`).
* **State Invalidation on Modification:** `modify_order` recalculates budget reservations and immediately marks associated approvals as invalid (`valid=False`), even if already `APPROVED`.
* **Discount Safeguards:** `request_discount` enforces a 10% ceiling, restricts discounts to one per quote, and rejects requested prices that are not strictly below the current unit price.

#### D. Environment Wrapper & State Generator (`src/environment/env.py`, `src/environment/tasks.py`)
* `ProcurementEnv`: Unified interface for executing an action, applying fault injection, and logging the step.
* Synthetic task generator (`generate_procurement_task(seed)`) to generate solvable scenarios with subtle traps (e.g., lowest quote is expired or from a suspended supplier).

---

### 2. Phase 2: Tasks Dataset & Ground-Truth Oracle

#### A. 20 Benchmark Procurement Tasks (`tasks/build_tasks.py`, `tasks/tasks.jsonl`)
* Structured dataset with 11 task families across 3 difficulty levels:
  * **7 Easy Tasks (T01–T07):** Direct single-order procurement, clear vendor selection.
  * **8 Medium Tasks (T08–T15):** Budget limits requiring discounts, multi-item coordination, approval workflows, invoice disputes.
  * **5 Hard Tasks (T16–T20):** Multi-project constraints, complex modifications invalidating approvals, tight budget trade-offs.
* Every task includes:
  * Natural language user `goal`.
  * Initial world state.
  * `reference_solution`: A sequence of valid actions that cleanly passes.
  * Sabotaged negative trajectories: Intentional flaw cases that verify the oracle catches failures.

#### B. Deterministic Evaluation Oracle (`src/evaluation/oracle.py`)
* **Zero-LLM dependency:** Completely machine-checkable logic (tested to ensure no LLM libraries are imported).
* **Always-On Invariant Checks:**
  1. Budget limits never exceeded.
  2. Vendors chosen are active and eligible (not suspended).
  3. Quotes used were valid at order time.
  4. No duplicate active purchase orders.
* **Task-Specific Checks:** Matching final PO statuses, item quantities, invoice clearances, and approval validity.
* Validation test script `scripts/validate_tasks.py` validates that all 20 reference trajectories PASS and all sabotaged negatives FAIL.

---

### 3. Phase 3: Fault Injector & Deterministic Replay

#### A. Overhauled Fault Injector (`src/faults/injector.py`)
* **Fixed `stale_info`:** Previously, the internal state was updated before the fault was generated, causing stale faults to be no-ops. Now correctly serves outdated information.
* **Fixed `timeout`:** Previously caught and silenced by an internal `try/except`. Now properly raises or simulates timeouts.
* **Cryptographic Per-Call Seed Hashing:**
  $$\text{hash} = \text{SHA-256}(\text{seed} \parallel \text{tool\_name} \parallel \text{serialized\_args} \parallel \text{occurrence})$$
  * **Significance:** In Policy A vs Policy B, Policy B makes extra verification queries. In a standard pseudo-random number generator, this would shift subsequent random numbers. With keyed hashing, the exact same agent action receives the exact same fault regardless of which policy is running!
* **Realistic Write Failures:** A simulated timeout on a write action (e.g., `create_purchase_order`) still executes the change on the backend simulator. If an agent naively retries without checking existing orders, a duplicate order is created, naturally triggering the oracle's duplicate detector.

#### B. Replay System (`src/faults/replay.py`)
* `replay_records()` re-executes saved trajectories to detect non-deterministic deviations.
* `ReplayInjector` replays recorded observations for deterministic debugging without re-rolling RNG.

---

### 4. Phase 4: LangGraph Agent & Experiment Runner

#### A. LangGraph Pipeline (`src/agent/graph.py`)
* **Execution Flow:**
  $$\text{init} \longrightarrow \text{agent} \longrightarrow \text{tool\_exec} \longrightarrow \text{fault\_injection} \longrightarrow \text{policy\_router} \longrightarrow \text{observe} \longrightarrow \begin{cases} \text{agent} \\ \text{finalize} \end{cases}$$
* **Strict Single Tool Call Execution:** Disables parallel tool calling to keep trajectory traces linear and reproducible.
* **Loop Prevention & Termination:**
  * Explicit `finish(status, summary)` tool.
  * Stop condition on pure text responses (`no_tool_call`).
  * Enforced `max_steps` (default 30) plus LangGraph recursion depth limit.
* **Observation Isolation:** Ground truth state is segregated. The agent LLM only sees the corrupted/faulty observation; the true state is passed directly to the Oracle.

#### B. Execution CLI & Providers (`run_agent.py`, `src/agent/llm.py`)
* **Providers:**
  * `--provider scripted`: Plays back the deterministic reference trajectory open-loop (allows running tests and sanity checks without any API keys).
  * `--provider anthropic`: Uses Claude models (`claude-haiku-4-5` by default) via `langchain-anthropic`.
* **Trajectory Logger (`src/agent/trajectory.py`):**
  * Emits rich JSONL logs capturing: true output, observed output, injected fault type, policy verification decision, agent reasoning tokens, and step latency.

---

## File Diff Breakdown (Against Your Previous Commit `10694f7`)

| File / Directory | Change | Purpose |
| :--- | :---: | :--- |
| `run_agent.py` | **Added** | CLI entry point to run single or all tasks with configurable policy and fault rates |
| `run_simulation.py` | **Updated** | Updated to use the new `ProcurementEnv` and task generator |
| `scripts/validate_tasks.py` | **Added** | Dataset validation runner checking all 20 reference & negative tasks |
| `src/agent/` | **Added** | LangGraph implementation (`graph.py`), prompts, LLM client, trajectory logger |
| `src/environment/tools.py` | **Added** | Complete schema definitions and risk levels for 17 tools |
| `src/environment/env.py` | **Added** | `ProcurementEnv` wrapper for step execution + fault injection |
| `src/environment/tasks.py` | **Added** | Task loading and synthetic procurement world generator |
| `src/environment/simulator.py` | **Refactored** | Enforced workflow state transitions, sequential IDs, quote pricing |
| `src/evaluation/oracle.py` | **Refactored** | Strict ground-truth invariants, zero LLM dependency |
| `src/faults/injector.py` | **Refactored** | Fixed stale/timeout bugs, per-call cryptographic seed hashing |
| `src/faults/replay.py` | **Added** | Episode replay engine and trace diffing |
| `tasks/build_tasks.py` | **Added** | Builder script generating `tasks.jsonl` with 20 tasks and negative cases |
| `tasks/tasks.jsonl` | **Updated** | 20 validated benchmark tasks |
| `tests/environment/` | **Removed** | Prototype tests removed in favor of unified test suite |
| `tests/test_simulator.py` | **Added** | 20 comprehensive unit tests for simulator behavior |
| `tests/test_tasks_oracle.py` | **Added** | Unit tests for oracle rules and task generation |
| `tests/test_injector.py` | **Added** | Unit tests verifying all 8 fault types, replay, and seed consistency |
| `tests/test_agent.py` | **Added** | Unit tests for LangGraph state graph, step limits, and finish calls |
| `docs/PHASES_1-4.md` | **Added** | Summary of design choices and phase exit criteria |
| `costaware-fork-main-phases1-4.patch` | **Added** | Complete diff patch backup |

---

## Recommended Next Steps

With Phases 1–4 complete and 173 tests passing:
1. **Push the merged branch to GitHub:**
   ```powershell
   git push origin siddharth_branch
   ```
2. **Begin Phase 5 (Self-Verification Node):**
   * Implement the `VerdictCache` (SQLite / in-memory cache) to avoid redundant verification costs.
   * Implement the LLM self-verifier in `src/verifier/` that inspects tool calls flagged by `policy_router`.
   * Implement tiered recovery limits (`low: 1`, `medium: 1`, `high: 2`).
