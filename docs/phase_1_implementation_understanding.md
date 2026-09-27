# Phase 1 Implementation Understanding

## 1. Purpose of This Document

This document describes the implementation that currently exists in the `costAware` repository after Phase 1 validation. It is intended to let a developer understand the working simulator, its data model, its tool contracts, its deterministic behavior, and the boundaries around later-phase components without rediscovering those facts from source code.

The descriptions below are based on the current files, not only on the original research plan. Where the plan and implementation differ, the difference is recorded explicitly.

Phase 1 is treated as the accepted baseline. This document does not change implementation code, tests, dependencies, or the later-phase components.

## 2. Project Research Context

The project is **Cost-Aware Adaptive Verification for Long-Horizon LLM Agents**. Its research question is whether a tool-using LLM agent can decide when verification is valuable, maintaining reliability while reducing verification cost compared with verifying every action.

The deterministic procurement simulator is the controlled environment in which those decisions will eventually be evaluated. It provides:

- A synthetic enterprise procurement and operations world.
- Explicit state-changing tools and validation rules.
- Reproducible initial states and transitions.
- A hidden ground-truth state that can later be evaluated by an oracle.
- Direct Python execution independent of an LLM or external API.

The simulator must exist independently before an LLM agent because environment behavior, tool outcomes, state transitions, and task success need to be testable without model variability. Otherwise, failures could not be cleanly attributed to the agent, verification policy, fault injection, or environment behavior.

Phase 1 establishes the environment baseline. Agent orchestration, self-verification, recovery, and adaptive experiments are later concerns even though some compatibility code for those concerns already exists in the repository.

## 3. Current Repository Structure

The following tree reflects the current meaningful source and project files. Generated caches such as `__pycache__/` and `.pytest_cache/` are omitted from the conceptual tree.

```text
costAware/
├── .env.example
├── .gitignore
├── IMPLEMENTATION.md
├── README.md
├── requirements.txt
├── run_simulation.py
├── Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md
├── docs/
│   ├── .gitkeep
│   └── phase_1_implementation_understanding.md
├── experiments/
│   └── .gitkeep
├── logs/
│   └── .gitkeep
├── results/
│   └── .gitkeep
├── scripts/
│   └── install_dependencies.py
├── src/
│   ├── __init__.py
│   ├── agent/
│   │   └── .gitkeep
│   ├── environment/
│   │   ├── __init__.py
│   │   ├── entities.py
│   │   ├── simulator.py
│   │   └── state.py
│   ├── evaluation/
│   │   ├── __init__.py
│   │   └── oracle.py
│   ├── faults/
│   │   ├── __init__.py
│   │   └── injector.py
│   ├── policies/
│   │   ├── __init__.py
│   │   └── policies.py
│   └── verifier/
│       └── .gitkeep
├── tasks/
│   ├── .gitkeep
│   └── tasks.jsonl
└── tests/
    ├── __init__.py
    └── environment/
        ├── __init__.py
        ├── test_determinism.py
        ├── test_entities.py
        ├── test_scenarios.py
        ├── test_simulator.py
        └── test_state_transitions.py
```

### Directory and file status

| Location | Current purpose and contents | Status / phase |
|---|---|---|
| `docs/` | Documentation directory. It contains `.gitkeep` and this Phase 1 understanding document. | Active documentation; this document is Phase 1 architecture documentation. |
| `experiments/` | Contains only `.gitkeep`. No experiment runner is currently implemented there. | Placeholder for later experiments. |
| `logs/` | Contains only `.gitkeep`. Runtime logs are not written there by the Phase 1 simulator itself. | Placeholder for later logging and experiment output. |
| `results/` | Contains only `.gitkeep`. No result tables or figures are currently committed. | Placeholder for later evaluation results. |
| `scripts/` | Contains `install_dependencies.py`, which installs or checks `requirements.txt`. | Utility support; not part of simulator execution. |
| `src/agent/` | Contains only `.gitkeep`. No LLM agent implementation exists. | Placeholder; later agent phase. |
| `src/environment/` | Contains the Phase 1 entities, hidden state model, simulator, registry, tool methods, and initial-state generator. | Active Phase 1 implementation. |
| `src/evaluation/` | Contains `oracle.py`, a deterministic true-state comparison helper. | Later-phase compatibility code; labelled Phase 2 in the source. |
| `src/faults/` | Contains `injector.py`, a seeded observation-corruption helper. | Later-phase compatibility code; labelled Phase 3 in the source. |
| `src/policies/` | Contains `policies.py`, including Policies A-E and a budget controller. | Later-phase policy code; source labels it Phase 6 and Phase 10 for parts of the file. |
| `src/verifier/` | Contains only `.gitkeep`. No verifier implementation exists. | Placeholder; later self-verification phase. |
| `tasks/` | Contains an empty starter `tasks.jsonl` file with a module comment and `.gitkeep`. | Dataset placeholder; not a populated Phase 2 task set. |
| `tests/environment/` | Contains entity, simulator, transition, determinism, and representative scenario tests. | Active Phase 1 validation. |

### Repository-level files

- `README.md` describes the research objective, broad pipeline, repository layout, policies, and evaluation dimensions.
- `requirements.txt` lists the broad project dependency set, including Pydantic, pytest, LangGraph, provider SDKs, numerical libraries, and reporting libraries.
- `.env.example` contains placeholder Anthropic and OpenAI API variables plus deterministic defaults. Phase 1 does not require those API keys.
- `.gitignore` excludes Python caches, virtual environments, `.env`, IDE files, and generated logs/results.
- `IMPLEMENTATION.md` summarizes the planned technology stack and intended later architecture. It is not a complete description of what is currently implemented.
- `Cost_Aware_Adaptive_Verification_Updated_Implementation_Plan.md` is the detailed design and phase plan. This document reports where the current code differs from it.
- `run_simulation.py` is a deterministic demonstration script that manually composes the simulator with the existing injector, policy router, and oracle.

## 4. Phase 1 Architecture

The actual Phase 1 execution path is:

```text
Pydantic entity models
        |
        v
SimulatorState (hidden true state)
        |
        v
ProcurementSimulator + TOOL_REGISTRY
        |
        v
Tool input validation
        |
        v
Explicit state transition or read-only computation
        |
        v
Structured Python dictionary result
        |
        v
Updated final true state
```

The owning components are:

1. **Entities** - `src/environment/entities.py` defines the Pydantic models, enums, computed totals, and field constraints.
2. **Simulator state** - `src/environment/state.py` defines `SimulatorState`, the complete hidden world model.
3. **Tool registry and dispatch** - `TOOL_REGISTRY` and `ProcurementSimulator.get_tools()` are both implemented in `src/environment/simulator.py`. There is no `src/environment/tools.py`.
4. **Validation** - Each simulator method validates its own inputs and referenced entities before mutation. Pydantic validates model construction.
5. **Transitions** - `ProcurementSimulator` methods explicitly mutate orders, approvals, quotes, budgets, and the simulator clock.
6. **Results** - Methods return ordinary structured dictionaries containing success data or an `error` field. There is no common result class.
7. **True state** - `ProcurementSimulator._true_state` is the ground truth used by the simulator. The public `state` property exposes it for oracle/test access; a future agent is expected to use tool results instead.

The current Phase 1 simulator does not itself inject faults, call an LLM, route through LangGraph, or perform adaptive verification.

## 5. Entities

All entities are Pydantic `BaseModel` classes in `src/environment/entities.py`. The model layer provides type-shaped structured data and selected numeric validation. It does not enforce every possible cross-entity business invariant.

### Vendor

`Vendor` represents a supplier.

Fields:

- `id: str`
- `name: str`
- `eligible: bool = True`
- `approved: bool = True`
- `suspended: bool = False`
- `preferred: bool = False`
- `payment_profile: str = "standard"`

PO creation requires the vendor to exist, be eligible, not suspended, and approved. Vendor status and details are exposed through read-only tools.

### Component

`Component` represents a product or procurement component.

Fields:

- `id: str`
- `name: str`
- `category: str`
- `reference_price: float`, constrained to be non-negative
- `required_qty: int`, constrained to be greater than zero
- `available_qty: int`, constrained to be non-negative

PO creation and modification reject a quantity greater than available quantity. The component itself is not decremented by PO creation in the current implementation.

### SupplierQuote

`SupplierQuote` links a vendor to a component and provides commercial terms.

Fields:

- `id: str`
- `vendor_id: str`
- `component_id: str`
- `unit_price: float`, greater than zero
- `quantity: int`, greater than zero
- `expiry_days: int`, greater than zero
- `shipping_cost: float`, non-negative and defaulting to zero
- `status: QuoteStatus`, defaulting to `ACTIVE`

The `total_price` property computes `unit_price * quantity + shipping_cost`. Quote expiry is evaluated against `SimulatorState.step`; the quote object is not automatically changed to `EXPIRED` by the clock.

### Project

`Project` groups procurement work and identifies its budget.

Fields:

- `id: str`
- `name: str`
- `owner: str`
- `budget_id: str`
- `procurement_rules: dict`, default empty
- `priority: str = "normal"`

The simulator uses `budget_id` to find the budget during PO creation, modification, release, and cancellation. A common rule is `require_approval_above`, but the current simulator does not automatically enforce that rule; approval is requested explicitly by the caller.

### Budget

`Budget` tracks financial allocation and commitments.

Fields:

- `id: str`
- `allocated: float`, non-negative
- `spent: float`, non-negative and default zero
- `reserved: float`, non-negative and default zero
- `remaining` property, calculated as `allocated - spent - reserved`

The simulator reserves a PO total at creation, adjusts the reservation when a PO is modified, moves reservation to spent when a PO is released, and frees reservation when a PO is cancelled.

### PurchaseOrder

`PurchaseOrder` represents an order. The current implementation uses one component per PO rather than an `items` collection.

Fields:

- `id: str`
- `vendor_id: str`
- `component_id: str`
- `quantity: int`, greater than zero
- `unit_price: float`, greater than zero
- `shipping_cost: float`, non-negative and default zero
- `project_id: str`
- `status: POStatus`, default `DRAFT`
- `approval_id: Optional[str]`, default `None`
- `released: bool`, default `False`
- `total` property, calculated as `unit_price * quantity + shipping_cost`

The lifecycle is normally `DRAFT -> PENDING_APPROVAL -> APPROVED -> RELEASED`. A draft or pending PO may be cancelled; a released or already cancelled PO cannot be cancelled.

### Approval

`Approval` represents an approval request associated with a PO.

Fields:

- `id: str`
- `po_id: str`
- `requester: str`
- `approver: str`
- `level: str`
- `status: ApprovalStatus`, default `PENDING`
- `valid: bool`, default `True`

A PO modification invalidates its current approval, sets its status to `INVALIDATED`, sets `valid` to `False`, returns the PO to draft, and clears the PO approval reference.

### Invoice

`Invoice` represents an invoice associated with a PO.

Fields:

- `id: str`
- `po_id: str`
- `amount: float`
- `line_items: List[dict]`, default empty
- `mismatch: bool`, default `False`
- `status: str`, default `"unpaid"`

The Phase 1 simulator provides `check_invoice()` for inspection. It does not create, pay, reconcile, or mutate invoices.

### Shipment

`Shipment` represents a shipment associated with a PO.

Fields:

- `id: str`
- `po_id: str`
- `quantity: int`
- `destination: str`
- `status: ShipmentStatus`, default `NOT_DISPATCHED`

The shipment entity exists in the state model, but no shipment-facing research tool is included in the 16-tool registry. Shipment behavior is therefore data-model support rather than an active Phase 1 workflow.

### Enums

The module defines:

- `POStatus`: `NOT_CREATED`, `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `RELEASED`, `CANCELLED`.
- `ApprovalStatus`: `PENDING`, `APPROVED`, `REJECTED`, `INVALIDATED`.
- `QuoteStatus`: `ACTIVE`, `EXPIRED`, `USED`.
- `ShipmentStatus`: `NOT_DISPATCHED`, `DISPATCHED`, `DELIVERED`.

## 6. Simulator State

`src/environment/state.py` defines `SimulatorState`, a Pydantic model containing the complete world:

```python
class SimulatorState(BaseModel):
    vendors: Dict[str, Vendor]
    components: Dict[str, Component]
    quotes: Dict[str, SupplierQuote]
    projects: Dict[str, Project]
    budgets: Dict[str, Budget]
    orders: Dict[str, PurchaseOrder]
    approvals: Dict[str, Approval]
    invoices: Dict[str, Invoice]
    shipments: Dict[str, Shipment]
    step: int
```

All collections default to empty dictionaries, and `step` defaults to zero. The state model does not separately contain agent observations, faults, policy decisions, verifier verdicts, or recovery attempts.

`ProcurementSimulator.load(state)` makes two deep Pydantic copies:

- `_initial_state` is the reset snapshot.
- `_true_state` is the mutable state used for execution.

This means later mutation of the loaded simulator state does not mutate the original state object passed to `load()`.

`reset()` deep-copies `_initial_state` back into `_true_state` and resets deterministic PO and approval counters to zero. Calling `reset()` before `load()` raises an assertion error.

The true-state boundary is conceptual and API-based rather than enforced with access control. The simulator tools operate on `_true_state`; future fault injection is expected to corrupt returned observations, not this state. The `state` property is intentionally available for tests and future oracle evaluation, so code running with simulator access can technically inspect it.

## 7. Simulator

`src/environment/simulator.py` defines `ProcurementSimulator`, `TOOL_REGISTRY`, and `generate_initial_state()`.

### Constructor and initialization

The constructor initializes:

- `_true_state = None`
- `_initial_state = None`
- `_po_counter = 0`
- `_approval_counter = 0`

`load(state)` establishes the initial and current deep-copied states. The simulator is not automatically populated in its constructor.

The `state` property returns the current true state. `advance_step()` increments the simulator clock used for quote expiry checks.

### Registry and dispatch

`get_tools()` copies every registry metadata dictionary, attaches the bound simulator method under the `callable` key, and returns the resulting dispatch mapping. `get_tool_names()` returns the registry keys.

### Read-only and compute methods

The read and compute methods query true state and return dictionaries. They do not intentionally mutate state:

- `search_vendors()` lists vendor IDs, names, and preferred flags.
- `get_vendor_details(vendor_id)` returns profile and eligibility fields.
- `check_vendor_status(vendor_id)` returns approval, suspension, and eligibility fields.
- `get_quotes(component_id)` returns matching quote data and a calculated `expired` flag.
- `check_quote_validity(quote_id)` returns quote status, expiry, and the current expired calculation.
- `check_budget(budget_id)` returns allocated, spent, reserved, and remaining values.
- `check_existing_orders(project_id)` lists matching orders.
- `compare_quotes(quote_ids)` returns known quotes sorted by total price.
- `check_invoice(invoice_id)` returns invoice fields.

Unknown IDs generally produce a dictionary containing an `error` field. An unknown component in `get_quotes()` produces an empty quote list rather than an error because the method filters the quote collection.

### State-changing method flow

Each write method follows the same broad pattern:

```text
Receive structured Python arguments
        |
Validate IDs, statuses, numeric values, and business constraints
        |
Mutate only after validation succeeds
        |
Return a structured dictionary
```

The exact transitions are documented in Section 9.

### Error handling and atomicity

Errors are returned as dictionaries instead of raised exceptions for normal invalid tool operations. Validation is performed before counters, collections, approvals, or budgets are changed. The test suite checks that failed operations do not partially mutate state.

Pydantic construction errors are the exception to this tool-result convention: invalid entity construction raises `ValidationError`.

## 8. Tool Registry and Tool Contracts

There is no `src/environment/tools.py`. The registry is defined directly in `src/environment/simulator.py` as `TOOL_REGISTRY`. It contains exactly 16 research-facing tools.

Each registry entry contains:

- `risk`: `low`, `medium`, or `high`.
- `type`: `read`, `compute`, or `write`.
- `mutates_state`: an explicit boolean.
- `description`.

`get_tools()` adds the bound callable for dispatch. The registry metadata is therefore machine-readable, while input schemas remain Python method signatures rather than separate Pydantic request/response classes.

| Tool | Purpose | Risk | Read/Write | Mutates State | Important Inputs | Result |
|---|---|---:|---|---:|---|---|
| `search_vendors()` | List candidate vendors. | low | read | No | None | `vendors` list. |
| `get_vendor_details()` | Inspect one vendor profile. | low | read | No | `vendor_id` | Vendor fields or `error`. |
| `check_vendor_status()` | Inspect approval, suspension, and eligibility. | low | read | No | `vendor_id` | Status fields or `error`. |
| `get_quotes()` | Retrieve quotes for a component. | low | read | No | `component_id` | `quotes` list with totals and expiry flag. |
| `check_quote_validity()` | Evaluate one quote at the current step. | low | read | No | `quote_id` | Quote status and `expired`, or `error`. |
| `check_budget()` | Inspect budget usage. | low | read | No | `budget_id` | Allocation and balance fields, or `error`. |
| `check_existing_orders()` | List project orders. | low | read | No | `project_id` | `orders` list. |
| `compare_quotes()` | Rank known quotes by total price. | low | compute | No | `quote_ids` | `ranked_quotes` list. |
| `request_discount()` | Apply an allowed quote price reduction. | medium | write | Yes, on success | `vendor_id`, `quote_id`, `requested_price` | Success and new price, or reason/error. |
| `create_purchase_order()` | Create a draft PO and reserve budget. | high | write | Yes, on success | vendor, component, quantity, price, project, shipping | PO ID, status, and total, or error. |
| `modify_order()` | Change quantity or unit price on a draft/pending PO. | high | write | Yes, on success | `po_id`, optional quantity/price | Modified status and approval invalidation, or error. |
| `request_approval()` | Create a pending approval for a draft PO. | medium | write | Yes, on success | `po_id`, `requester` | Approval ID and pending status, or error. |
| `approve_order()` | Approve a pending valid approval. | high | write | Yes, on success | `approval_id` | Approved approval and PO, or error. |
| `release_order()` | Release an approved PO and move budget to spent. | high | write | Yes, on success | `po_id` | Released status, or error. |
| `cancel_order()` | Cancel an eligible PO and free reservation. | high | write | Yes, on success | `po_id` | Cancelled status, or error. |
| `check_invoice()` | Inspect invoice fields. | low | read | No | `invoice_id` | Invoice fields or `error`. |

The tool methods return ordinary dictionaries, not a common typed result envelope. Successful writes usually identify the affected object and status. Failures generally include an `error` string and, for insufficient budget, remaining and required amounts. This is sufficient for the Phase 1 direct-Python tests, but a later agent/tool protocol may add formal request and response schemas.

## 9. State Transitions

### Creating a purchase order

Call:

```python
sim.create_purchase_order(
    vendor_id, component_id, quantity, unit_price,
    project_id, shipping_cost=0.0
)
```

Validation occurs in this order:

1. Vendor exists.
2. Vendor is eligible and not suspended.
3. Vendor is approved.
4. Component exists.
5. Quantity is positive.
6. Unit price is positive.
7. Shipping cost is non-negative.
8. Project exists.
9. The project budget exists if one is referenced; if present, its remaining amount must cover the total.
10. Quantity must not exceed component availability.

The total is `unit_price * quantity + shipping_cost`. After successful validation, the PO counter increments, a deterministic ID such as `PO-001` is assigned, a `DRAFT` PO is inserted into `state.orders`, and the total is added to `budget.reserved`.

The component availability and quote status are not changed by PO creation.

### Modifying a purchase order

Call:

```python
sim.modify_order(po_id, quantity=None, unit_price=None)
```

The PO must exist and be `DRAFT` or `PENDING`. At least one field must be supplied. A supplied quantity must be positive and within component availability. A supplied unit price must be positive.

The simulator calculates the proposed new total before mutation. If a budget exists, the available amount is calculated as current remaining plus the PO's old total, and the new total must fit. The reservation is then adjusted by:

```text
new_total - old_total
```

If the PO has an approval, that approval is marked invalid with `ApprovalStatus.INVALIDATED` and `valid=False`. The PO returns to `DRAFT` and its `approval_id` is cleared. The result reports that the order was modified and approval was invalidated.

Invalid modifications return before changing the PO, approval, budget, or counters.

### Requesting approval

Call:

```python
sim.request_approval(po_id, requester)
```

The PO must exist, be `DRAFT`, and have a non-empty requester. The approval counter increments and creates an `Approval` with deterministic ID such as `APR-001`, requester, fixed approver `manager`, level `manager`, and pending status. The PO changes to `PENDING` and references the approval.

A second approval request for the same pending PO is rejected.

### Approving an order

Call:

```python
sim.approve_order(approval_id)
```

The approval must exist, remain valid, and be `PENDING`. Its PO must exist and also be `PENDING`. The approval becomes `APPROVED` and the PO becomes `APPROVED`.

An invalidated approval, missing PO, or approval in another status is rejected without mutation.

### Releasing an order

Call:

```python
sim.release_order(po_id)
```

The PO must exist and be `APPROVED`. The PO changes to `RELEASED` and `released=True`. Its project budget is found, the PO total is subtracted from `reserved`, and the same total is added to `spent`.

A draft, pending, cancelled, or missing PO cannot be released.

### Cancelling an order

Call:

```python
sim.cancel_order(po_id)
```

The PO must exist and must not already be `RELEASED` or `CANCELLED`. The PO becomes `CANCELLED`. If its project and budget exist, its total is removed from the reserved amount using a lower bound of zero.

The current implementation does not create a cancellation event or shipment effect. It also does not separately change an approval record when cancelling a PO.

### Requesting a discount

Call:

```python
sim.request_discount(vendor_id, quote_id, requested_price)
```

The vendor and quote must exist, and the quote must belong to the supplied vendor. The requested price must be positive. A request succeeds only when it is lower than the current price but no more than 10 percent below it, meaning it is at least 90 percent of the current price.

On success, the quote's `unit_price` is changed. A request outside the allowed range returns `success=False` and does not mutate the quote.

## 10. Determinism

### Seeded initial-state generation

`generate_initial_state(seed=42)` creates a new `random.Random(seed)` instance. It does not use the global random generator.

The generator deterministically creates:

- Five named vendors, with `V5` always suspended.
- Four components.
- One to three quotes per component where eligible vendors are available.
- Two projects and corresponding budgets.
- Deterministically calculated prices, quantities, expiry values, shipping values, priorities, and procurement rules.

The returned `SimulatorState` is deterministic for a given seed. Different seeds produce different generated states in the tests.

### Deterministic trajectories

PO and approval IDs use counters instead of UUIDs:

- First PO: `PO-001`.
- First approval: `APR-001`.

The counters increment only on successful creation and reset to zero in `reset()`.

The determinism guarantee tested by the repository is:

```text
same seed
    -> equal initial SimulatorState

same initial state + same valid tool sequence
    -> equal tool results and equal final SimulatorState

mutate state + reset()
    -> exact initial state and reset counters
```

### Confirmed tests

`tests/environment/test_determinism.py` covers same-seed equality, different-seed variation, generated-world contents, identical trajectories, reset restoration, and counter reset. The Phase 1 validation also directly checked read-only preservation and reset behavior.

## 11. Tests

The repository test suite is Python/pytest based and does not use an LLM or external API.

| Test File | What It Tests | Important Cases |
|---|---|---|
| `tests/environment/test_entities.py` | Entity construction, enum values, computed properties, and model validation. | Vendor defaults, quote and PO totals, budget remaining, invalid component quantities, invalid PO prices, invoice and shipment construction. |
| `tests/environment/test_simulator.py` | Simulator setup, registry, all tool methods, deterministic IDs, and write-tool error paths. | Registry metadata and callable dispatch, read-only tools, quote validity, budget checks, PO creation, discounts, approval, modification, release, cancellation, and failed-operation integrity. |
| `tests/environment/test_state_transitions.py` | Explicit PO lifecycle, approval invalidation, budget flows, and invalid transitions. | Draft-to-release lifecycle, cancellation, release restrictions, modification restrictions, approval re-request, reservation reconciliation, insufficient budget, and atomic failure. |
| `tests/environment/test_determinism.py` | Seed generation, trajectory reproducibility, reset behavior, and ID counter reproducibility. | Same seed, different seed, same state plus same actions, multiple runs, reset equality, and reset IDs. |
| `tests/environment/test_scenarios.py` | Ten direct-Python representative simulator scenarios. | Vendor search/details/status, quote retrieval/expiry/comparison, budgets, valid PO, approval, and full procurement workflow. |

The recorded Phase 1 validation evidence is:

- Full test suite: **131 passed**.
- Representative scenario module: **16 passed**.
- Ten representative direct-Python scenarios demonstrated.
- Same-seed deterministic generation verified.
- Read-only state preservation verified.
- `reset()` verified.
- No LLM or external API required.

The ten scenario classes in `test_scenarios.py` establish the Phase 1 exit criterion. The module contains 16 tests distributed across those ten scenario categories.

## 12. Representative Scenarios

These are simulator validation scenarios, not the final Phase 2 task dataset.

| # | Scenario | Important calls | Expected behavior | Result |
|---:|---|---|---|---|
| 1 | Basic vendor search | `search_vendors()` | All configured vendors are returned and preferred status is preserved. | PASS |
| 2 | Vendor inspection | `get_vendor_details()` | Eligible and suspended vendor details are reported accurately. | PASS |
| 3 | Vendor status | `check_vendor_status()` | Approval, suspension, and eligibility flags are exposed. | PASS |
| 4 | Quote retrieval | `get_quotes()` | Quotes are filtered by component and include calculated totals. | PASS |
| 5 | Quote validity | `advance_step()`, `check_quote_validity()` | A quote becomes reported as expired after its expiry step. | PASS |
| 6 | Budget validation | `check_budget()` | Allocated, spent, reserved, and remaining values are correct. | PASS |
| 7 | Quote comparison | `compare_quotes()` | Candidate quotes are ranked by total cost including shipping. | PASS |
| 8 | Valid PO and existing-order inspection | `create_purchase_order()`, `check_budget()`, `check_existing_orders()` | A valid draft PO is created and reserves its budget. | PASS |
| 9 | Approval workflow | `create_purchase_order()`, `request_approval()`, `approve_order()` | A draft PO becomes pending and then approved with a valid approval. | PASS |
| 10 | Full procurement workflow | vendor/quote/budget reads, `create_purchase_order()`, `request_approval()`, `approve_order()`, `release_order()` | The PO is released and reserved budget moves to spent. | PASS |

The tests also cover representative invalid cases such as suspended vendors, insufficient budgets, invalid transitions, invalidated approvals, cancelled orders, and failed operations that must not mutate state.

## 13. `run_simulation.py`

`run_simulation.py` is a hard-coded deterministic demonstration, not an LLM agent or LangGraph workflow.

It:

1. Builds a small task state directly in `build_task_001()`.
2. Loads that state into `ProcurementSimulator`.
3. Creates a seeded `FaultInjector`.
4. Calls simulator tools using a fixed action sequence in `simulated_agent_run()`.
5. Passes each clean simulator result through the fault injector.
6. Routes the observed result through `should_verify()` for a selected policy.
7. Records true result, observed result, fault type, verification decision, and reason in an in-memory trajectory.
8. Evaluates the simulator's true final state with `oracle_check()`.
9. Runs policies A, B, C, and D with the same fault seed and prints a summary.

The workflow is:

```text
manual task state
    -> ProcurementSimulator
    -> clean tool result
    -> FaultInjector observation
    -> should_verify policy decision
    -> trajectory log
    -> oracle_check(true state)
```

The script imports later-phase compatibility modules, but it does not implement an LLM, self-verifier, recovery loop, or LangGraph graph. Its hard-coded sequence is useful as a deterministic integration demonstration and must not be mistaken for the future research agent.

## 14. Components From Later Phases

### `src/evaluation/oracle.py`

`oracle_check(true_state, expected)` is implemented and labelled Phase 2. It is pure Python and never calls an LLM. It returns `(passed, checks)` and evaluates selected expectations including PO status, vendor eligibility, budget non-negativity, approval validity, suspended-vendor use, and quantity.

Status: **Implemented as an early deterministic oracle, but partial relative to the full design.** It does not check every possible objective such as component usage, duplicate orders, shipment state, or arbitrary task predicates.

Phase 2 should use or extend this component after defining the task schema and objective checks. Phase 1 simulator behavior should remain the source of true state and should not be merged with oracle logic.

### `src/faults/injector.py`

`FaultInjector` is implemented and labelled Phase 3. It uses `random.Random(seed)`, stores a per-tool stale cache, and can produce eight fault types: wrong value, stale information, contradictory boolean, malformed output representation, missing field, timeout, incorrect status, and corrupted numeric observation.

The `inject(tool_name, true_result)` method returns an observed result and fault type while preserving the supplied clean result for the caller. It deep-copies result data and does not mutate simulator state.

Status: **Implemented as a compatibility component, not a complete research harness.** It is not part of Phase 1 simulator execution. Its current `stale_info` path updates the cache immediately before reading it, so a real stale-result behavior is not demonstrated by the first call and may need review later. The malformed-output implementation returns a dictionary containing `raw` and `parse_error`, despite a comment describing a raw string. These are later-phase concerns.

Phase 2 should generally leave fault injection untouched unless task execution needs a defined observation wrapper or a concrete defect is demonstrated.

### `src/policies/policies.py`

`should_verify()` implements Policies A, B, C, D, and E. A never verifies; B always verifies; C verifies every three steps; D checks high-risk tools, schema/sanity failures, and low confidence; E uses a `BudgetController` and risk score. The module also defines the high-risk tool set and an EWMA-style budget controller.

Status: **Implemented policy routing code, but not a complete experimental system.** It does not call a verifier, execute recovery, or run an experiment by itself. The source labels it Phase 6 and describes Policy E as a later addition.

Phase 2 should define task execution and oracle integration without requiring an LLM agent. It should avoid treating this policy module as proof that adaptive verification experiments are complete.

### `src/verifier/`

The directory contains only `.gitkeep`.

Status: **Placeholder / not implemented.** No self-verifier code exists. Phase 2 should leave it untouched unless the later plan explicitly begins verifier work.

### `src/agent/`

The directory contains only `.gitkeep`.

Status: **Placeholder / not implemented.** No LLM agent or LangGraph graph exists. Phase 2 does not require an LLM agent.

## 15. Current Data Flow

A concrete direct-Python purchase-order workflow is:

```text
Construct SimulatorState
    |
    v
ProcurementSimulator.load(state)
    |
    v
sim.create_purchase_order(...)
    |
    v
Validate vendor, component, quantity, price, project, budget, availability
    |
    v
Create PurchaseOrder and reserve budget
    |
    v
Return {"po_id": ..., "status": "DRAFT", "total": ...}
    |
    v
sim.request_approval(po_id, requester)
    |
    v
Create Approval and set PO to PENDING
    |
    v
sim.approve_order(approval_id)
    |
    v
Set Approval and PO to APPROVED
    |
    v
sim.release_order(po_id)
    |
    v
Set PO to RELEASED; reserved budget -> spent budget
    |
    v
sim.state contains final true state
```

The direct calls operate synchronously in one Python process. Results are dictionaries returned to the caller. No observation corruption occurs unless the caller explicitly wraps the result with `FaultInjector`. No verification occurs unless the caller explicitly invokes a policy or later verifier. The simulator itself remains responsible only for true-state reads, validation, transitions, and clean results.

## 16. Research Architecture Mapping

| Research Concept | Current Implementation | Status |
|---|---|---|
| True simulator state | `SimulatorState` and `ProcurementSimulator._true_state` in `src/environment/`. | IMPLEMENTED for Phase 1. |
| Agent-visible observation | Clean dictionaries returned by simulator tools; optional corrupted copies from `FaultInjector` in a later wrapper. | PARTIAL; no agent exists. |
| Tool layer | Bound methods on `ProcurementSimulator`. | IMPLEMENTED. |
| Tool risk metadata | `TOOL_REGISTRY` entries with `risk`. | IMPLEMENTED. |
| Read/write metadata | `type` plus explicit `mutates_state` in `TOOL_REGISTRY`. | IMPLEMENTED. |
| Tool dispatch | `ProcurementSimulator.get_tools()` attaches `callable`. | IMPLEMENTED. |
| Fault injector | `FaultInjector.inject()` in `src/faults/injector.py`. | IMPLEMENTED as an early later-phase component. |
| Deterministic oracle | `oracle_check()` in `src/evaluation/oracle.py`. | PARTIAL relative to the full task objective design. |
| Task specification | `run_simulation.py` builds one task in Python; `tasks/tasks.jsonl` is only a starter/comment file with no populated records confirmed. | PARTIAL / placeholder. |
| Verification policy | `should_verify()` implements A-E in `src/policies/policies.py`. | PARTIAL; routing exists, verifier execution does not. |
| Self-verifier | No implementation under `src/verifier/`. | NOT YET IMPLEMENTED. |
| Recovery | No recovery implementation exists. | NOT YET IMPLEMENTED. |
| LLM agent | `src/agent/` contains only `.gitkeep`. | NOT YET IMPLEMENTED. |
| LangGraph orchestration | No LangGraph graph or node implementation exists. | NOT YET IMPLEMENTED. |
| Experiment runner | `experiments/` contains only `.gitkeep`; `run_simulation.py` is a manual demo. | NOT YET IMPLEMENTED. |
| Logging pipeline | `logs/` contains only `.gitkeep`; the demo keeps trajectory data in memory and prints it. | PARTIAL / placeholder. |

## 17. Phase 1 Boundary

### Phase 1 contains

- Deterministic procurement entities.
- Hidden simulator state.
- Deterministic initial-state generation.
- Simulator loading and reset.
- Read-only and compute tools.
- Medium- and high-risk write tools.
- Tool registry and dispatch metadata.
- Input validation and explicit state transitions.
- Budget reservation, release, cancellation, and modification behavior.
- Unit tests and direct-Python representative scenarios.
- No-LLM deterministic execution.

### Phase 1 does not require

- An LLM agent.
- LangGraph orchestration.
- A self-verifier.
- Recovery policy execution.
- Adaptive verification experiments.
- Policy comparison as a research result.
- Fault injection as a Phase 1 research variable.
- A final oracle-driven task benchmark.
- A large task dataset.

The repository contains later-phase compatibility modules, but their presence does not change the Phase 1 boundary or establish completion of those later phases.

## 18. What Phase 2 Will Build On

Phase 2 can consume the following stable Phase 1 interfaces:

- `SimulatorState` for initial and true final state.
- `ProcurementSimulator.load()` and `reset()` for repeatable trials.
- `ProcurementSimulator.get_tools()` and the 16 registered methods for tool execution.
- Structured dictionary results and `error` responses.
- Explicit PO, approval, budget, quote, vendor, invoice, and shipment state.
- `generate_initial_state(seed)` for reproducible environments.
- Deterministic PO and approval counters.
- The true-state boundary between simulator execution and future observations.
- Direct Python execution without an LLM.

The planned Phase 2 additions are expected to include approximately 20 tasks, task families, difficulty tiers, populated `tasks.jsonl` records, objective final-state specifications, a deterministic oracle contract, and reference trajectories. The current repository does not yet contain a confirmed populated 20-task dataset.

Phase 2 does not require an LLM agent. It should first make tasks and oracle evaluation deterministic and executable directly against the existing simulator. An LLM agent, LangGraph, self-verifier, and recovery belong to later boundaries.

## 19. Known Architectural Notes / Deviations

### Pydantic models instead of dataclasses/dicts

- Planned design: the implementation plan describes Python dataclasses/dictionaries as the state schema.
- Actual code: entities and `SimulatorState` are Pydantic `BaseModel` classes.
- Impact: harmless and useful for structured validation, copying, and computed properties. Future code should use the actual Pydantic API rather than assuming dataclasses.

### Registry is inside `simulator.py`

- Planned/documentation expectation: a separate tools module was considered.
- Actual code: `TOOL_REGISTRY`, dispatch metadata, and tool methods are all in `src/environment/simulator.py`; `tools.py` does not exist.
- Impact: harmless for Phase 1, but the simulator module owns more responsibilities than a future refactor might choose.

### Purchase orders are single-component records

- Planned entity description: Purchase Order includes items.
- Actual code: `PurchaseOrder` stores one `component_id`, one `quantity`, one `unit_price`, and shipping cost. There is no `items` list.
- Impact: acceptable for the current Phase 1 scenarios, but multi-line purchase orders would require a deliberate future schema change.

### Procurement rules are stored but not automatically interpreted

- Planned design: project procurement rules can determine approval requirements.
- Actual code: `Project.procurement_rules` stores a dictionary, but PO creation does not automatically request approval based on `require_approval_above`. The caller explicitly calls `request_approval()`.
- Impact: important task/oracle behavior to define before designing tasks that depend on automatic approval thresholds.

### Task dataset is not populated

- Planned design: Phase 2 is expected to create approximately 20 tasks.
- Actual code: `tasks/tasks.jsonl` contains only a starter comment and no confirmed task records. `run_simulation.py` constructs one task directly in Python.
- Impact: Phase 2 work remains necessary for a reusable benchmark dataset.

### Later-phase modules exist ahead of their complete phases

- Planned sequence: oracle, fault injection, policies, verifier, agent, and experiments are phased later.
- Actual code: oracle, fault injector, and policy routing already exist, while agent and verifier directories are placeholders.
- Impact: these modules are compatibility scaffolding or early implementations, not evidence that the associated research phases are complete.

### Observation corruption is external to the simulator

- Planned design: faults corrupt observations without changing true state.
- Actual code: `FaultInjector` is a separate caller-side helper that deep-copies result dictionaries. The simulator itself always returns clean results.
- Impact: this preserves the desired true-state separation. The injector's stale-information and malformed-output details should be reviewed in its own phase.

### No common typed tool-result envelope

- Planned requirement: structured success/failure contracts.
- Actual code: methods return dictionaries with tool-specific keys; failures usually contain `error`, while some operations use `success=False` and `reason`.
- Impact: sufficient for current tests, but a future agent protocol may benefit from a shared result schema.

### The demo composes later components

- Planned Phase 1 boundary: simulator validation is independent.
- Actual code: `run_simulation.py` imports the fault injector, policies, and oracle and manually demonstrates all four baseline policies.
- Impact: the simulator remains independently testable, but the demo is an integration demonstration spanning multiple planned phases and is not proof that an LLM workflow exists.

## 20. Phase 1 Completion Summary

Phase 1 is **COMPLETE and accepted as the repository baseline**.

Evidence:

- Full test suite: **131 passed**.
- Representative scenario tests: **16 passed**.
- Ten representative direct-Python scenarios were demonstrated.
- Same-seed initial-state generation was verified.
- Same state plus the same tool sequence produced the same final state.
- Read-only operations preserved true state.
- `reset()` restored the initial state and deterministic counters.
- No LLM or external API was required.

The current simulator provides the deterministic environment, entity models, hidden state, tool registry, validation, state transitions, and direct execution surface needed for the next phase. Phase 2 should build task specifications and deterministic objective evaluation on top of this baseline without rewriting the simulator unless a concrete compatibility defect is demonstrated.
