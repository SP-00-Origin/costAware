# Phases 1–4 — what was built and the decisions behind it

Status against the plan's exit criteria (Section 10).

| Phase | Exit criterion | Evidence |
|---|---|---|
| 1 · Simulator | ≥10 representative tasks execute correctly | all 20 reference trajectories run with zero tool errors (`scripts/validate_tasks.py`); 20 simulator unit tests |
| 2 · Tasks + Oracle | 20 validated tasks; oracle never depends on model judgment | `tasks/tasks.jsonl` (7 easy / 8 medium / 5 hard, 11 families); every reference PASSes, every empty and sabotaged trajectory FAILs for the intended reason; a test asserts the oracle imports no LLM library |
| 3 · Fault injector | all core fault types pass tests | 8/8 fault types tested; same seed → same faults; replay reproduces logged episodes exactly |
| 4 · LangGraph agent | no infinite loops; DONE works; trajectories inspectable | step limit + recursion backstop tested; `finish` tool; one JSONL per episode with true vs observed result, fault, and policy decision per step |

**Not yet shown for Phase 4:** "agent completes a meaningful subset of clean tasks" with a real LLM. That needs an
`ANTHROPIC_API_KEY`:

```bash
export ANTHROPIC_API_KEY=...
python run_agent.py --task all --provider anthropic            # clean environment
```

## Commands

```bash
pip install -r requirements.txt
python -m pytest tests -q                                       # 172 tests, no API key needed
python tasks/build_tasks.py && python scripts/validate_tasks.py # regenerate + validate the dataset
python run_simulation.py --task T17 --rate 0.4                  # deterministic pipeline demo
python run_agent.py --task all --provider scripted              # agent graph dry run (no key)
python run_agent.py --task T08 --provider anthropic --policy D --fault-rate 0.25 -v
```

## Phase 1 — simulator

- **Workflow vs policy rules.** The simulator enforces the workflow state machine and referential integrity
  (unknown IDs, illegal transitions, release above the project's approval threshold without a valid approval).
  It does **not** block policy mistakes: ordering from a suspended/unapproved vendor, overrunning the budget,
  ordering on an expired quote, duplicate orders. Those go through and the oracle fails them. The earlier code
  blocked suspended vendors and over-budget orders, which meant a fault could never lead to a failure and the
  policies could never differ.
- **Orders are priced from quotes.** `create_purchase_order(project_id, quote_id, quantity)` takes vendor, price
  and shipping from the quote, so the agent cannot invent a price.
- **Deterministic IDs** (`PO-0001`, `APR-0001`) instead of `uuid4`, so reruns are identical.
- **State transitions fixed:** `modify_order` adjusts the budget reservation and invalidates the approval even
  when the PO is already `APPROVED` (this is the "approval invalidated after modification" dependency); release
  checks the approval is still valid; cancel frees the reservation; discounts are capped at 10% and one per quote.
- **Approval threshold** (`procurement_rules.require_approval_above`) is now enforced; it was ignored before.
- **Tool registry** (`src/environment/tools.py`): 17 tools with risk tier, description and JSON schema. It is
  used for LLM tool-calling, argument validation, and Policy D's high-risk signal. One tool was added to the
  plan's 16: `dispute_invoice` (medium), so invoice-mismatch tasks have an action to resolve them.
- **Initial-state generator:** `generate_procurement_task(seed)` builds solvable new-procurement tasks with a
  trap (cheapest quote expired or from a suspended vendor). 50 seeds are validated in the tests.
- **`ProcurementEnv`** is the one place a tool call happens (execute → fault → record); every runner uses it.

## Phase 2 — tasks + oracle

- Tasks are written in `tasks/build_tasks.py`; `tasks.jsonl` is generated from it, and a test checks the two
  are in sync. Each task has `goal`, `initial_state`, `expected_final_state`, `reference_solution` and at least
  one `negatives` trajectory that must FAIL.
- **Oracle** (`src/evaluation/oracle.py`) has always-on checks: budgets within limits, vendor standing of every
  active order, quotes valid at order creation, no duplicate active orders. It also has per-task checks: required
  orders (vendor, quantity, status, price, valid approval), specific order states, invoice states, budget
  reservation, max new orders. Orders are found by project + component, not by a PO id the agent happened to
  get. Legacy keys from the prototype still work.

## Phase 3 — fault injector

- **Fixed:** `stale_info` was a no-op (the cache was refreshed before the fault was applied), and `timeout`
  never fired (the exception was swallowed by the injector's own `try`).
- **Per-call keyed randomness.** Each call's fault comes from `sha256(seed | tool | args | occurrence)`, not one
  shared stream. The same agent action therefore gets the same fault under Policies A–D, even though B makes
  extra verification calls. Re-calling a tool (recovery) is an independent roll.
- Faults now reach nested fields (e.g. one quote inside `get_quotes`). A fault that would not change the result
  is skipped, so every logged fault is a visible corruption.
- A timeout on a write tool still performs the write, which makes retries create duplicates. This is
  intentional: it is a realistic failure that verification should catch.
- **Replay** (`src/faults/replay.py`): `replay_records()` re-runs a logged trajectory and reports any divergence;
  `ReplayInjector` feeds back the exact recorded observations.
- Observed mix at rate 0.25 over 200 reference episodes: effective rate ≈24%. Fault types that always apply
  (malformed, missing field, timeout) occur more often than ones that need a particular field (stale, wrong
  value). Weight the types if a balanced mix is needed.

## Phase 4 — LangGraph agent

`src/agent/graph.py`: `init → agent → tool_exec → fault_injection → policy_router → observe → (agent | finalize)`.

- One structured tool call per turn (parallel tool use disabled). Any extra calls still get a tool result so
  the message history stays valid.
- `finish(status, summary)` ends the episode. A plain-text reply also ends it (`no_tool_call`), and so do
  `max_steps` (default 30) and LangGraph's recursion limit.
- Invalid tool names or arguments come back to the agent as error observations; they never touch state or
  crash the run. An API error ends the episode with `done_reason="error"` but keeps the log and oracle verdict.
- The agent only ever sees the observed result; the true result goes only to the log and oracle. This is tested.
- `policy_router` records `verify_decision` and `trigger_reason` per step. The verifier and recovery branch
  plugs in here in Phase 5 (`verifier_verdict` and `recovery_attempts` are already in the record).
- Model: `--provider anthropic` (default `claude-haiku-4-5`, override with `--model` or
  `COSTAWARE_AGENT_MODEL`), or `--provider scripted`. The scripted model replays the reference solution
  open-loop: useful for tests and as a never-adapting baseline.

## Not changed

- The policy logic for A–D (Phase 6); only made to read risk tags from the registry and to handle timeouts.
- `BudgetController` / Policy E.
