"""
oracle.py — Phase 2
The Deterministic Oracle. NEVER uses an LLM.
Compares the simulator's TRUE final state against the task's expected_final_state.
Returns PASS/FAIL + a structured diff.

Always-on checks (apply to every task)
--------------------------------------
budgets_within        every budget has remaining >= 0
vendor_standing       no active (non-cancelled) order uses a vendor that is
                      suspended, unapproved or ineligible
valid_quotes          every order created during the task used a quote that was
                      not expired at the step it was created
no_duplicate_orders   at most one active order per (project, component)

Task-specific checks (keys of expected_final_state)
---------------------------------------------------
orders: [ {project_id, component_id,                 # identifies the order
           vendor_id | vendor_in, quantity, status,   # optional field checks
           unit_price, max_unit_price, approval_valid} ]
    Exactly one active order must match project_id + component_id and
    satisfy every listed field.
order_states:   {po_id: status}         status of specific (usually pre-existing) orders
invoice_states: {invoice_id: status}    e.g. {"INV-2": "disputed", "INV-1": "unpaid"}
budget_reserved: {budget_id: amount}    exact reserved amount (e.g. 0 after cancelling)
max_new_orders: int                     orders the agent may create in total

Legacy keys from the first prototype (po_id + po_status, vendor_id, budget_id,
approval_required, no_suspended_vendor, expected_quantity) are still accepted.
"""
from typing import Any, Dict, List, Tuple

from ..environment.entities import ApprovalStatus, POStatus
from ..environment.state import SimulatorState

EPS = 0.01


def _active(order) -> bool:
    return order.status != POStatus.CANCELLED


def _check(expected, actual, passed) -> Dict[str, Any]:
    return {"expected": expected, "actual": actual, "pass": bool(passed)}


def _approval_valid(state: SimulatorState, po) -> bool:
    apr = state.approvals.get(po.approval_id) if po and po.approval_id else None
    return bool(apr and apr.status == ApprovalStatus.APPROVED and apr.valid)


def _vendor_ok(state: SimulatorState, vendor_id: str) -> bool:
    v = state.vendors.get(vendor_id)
    return bool(v and v.eligible and v.approved and not v.suspended)


def _always_on(state: SimulatorState, initial: SimulatorState = None) -> Dict[str, Dict[str, Any]]:
    checks = {}

    over = {b.id: round(b.remaining, 2) for b in state.budgets.values() if b.remaining < -EPS}
    checks["budgets_within"] = _check({}, over, not over)

    bad_vendor = sorted(o.id for o in state.orders.values()
                        if _active(o) and not _vendor_ok(state, o.vendor_id))
    checks["vendor_standing"] = _check([], bad_vendor, not bad_vendor)

    stale = []
    for o in state.orders.values():
        if o.created_step is None or not o.quote_id:
            continue
        q = (initial or state).quotes.get(o.quote_id) or state.quotes.get(o.quote_id)
        if q is None or q.is_expired(o.created_step):
            stale.append(o.id)
    checks["valid_quotes"] = _check([], sorted(stale), not stale)

    seen: Dict[Tuple[str, str], List[str]] = {}
    for o in state.orders.values():
        if _active(o):
            seen.setdefault((o.project_id, o.component_id), []).append(o.id)
    dups = {f"{p}/{c}": sorted(ids) for (p, c), ids in seen.items() if len(ids) > 1}
    checks["no_duplicate_orders"] = _check({}, dups, not dups)
    return checks


def _order_requirement(state: SimulatorState, req: Dict[str, Any]) -> Dict[str, Any]:
    matches = [o for o in state.orders.values()
               if _active(o) and o.project_id == req["project_id"]
               and o.component_id == req["component_id"]]
    if len(matches) != 1:
        return _check(req, {"matching_active_orders": sorted(o.id for o in matches)}, False)
    po = matches[0]
    actual = {"po_id": po.id, "vendor_id": po.vendor_id, "quantity": po.quantity,
              "status": po.status.value, "unit_price": po.unit_price,
              "approval_valid": _approval_valid(state, po)}
    ok = True
    if "vendor_id" in req:
        ok &= po.vendor_id == req["vendor_id"]
    if "vendor_in" in req:
        ok &= po.vendor_id in req["vendor_in"]
    if "quantity" in req:
        ok &= po.quantity == req["quantity"]
    if "status" in req:
        ok &= po.status.value == req["status"]
    if "unit_price" in req:
        ok &= abs(po.unit_price - req["unit_price"]) <= EPS
    if "max_unit_price" in req:
        ok &= po.unit_price <= req["max_unit_price"] + EPS
    if req.get("approval_valid"):
        ok &= actual["approval_valid"]
    return _check(req, actual, ok)


def _legacy(state: SimulatorState, expected: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    checks = {}
    po = state.orders.get(expected.get("po_id")) if expected.get("po_id") else None
    if "po_status" in expected:
        actual = po.status.value if po else "NOT_CREATED"
        checks["po_status"] = _check(expected["po_status"], actual, actual == expected["po_status"])
    if "vendor_id" in expected:
        ok = _vendor_ok(state, expected["vendor_id"])
        checks["vendor_eligible"] = _check(True, ok, ok)
    if "budget_id" in expected:
        b = state.budgets.get(expected["budget_id"])
        within = bool(b and b.remaining >= -EPS)
        checks["budget_not_exceeded"] = _check(True, within, within)
    if expected.get("approval_required"):
        valid = _approval_valid(state, po)
        checks["approval_valid"] = _check(True, valid, valid)
    if expected.get("no_suspended_vendor"):
        violated = any(_active(o) and state.vendors.get(o.vendor_id) and state.vendors[o.vendor_id].suspended
                       for o in state.orders.values())
        checks["no_suspended_vendor"] = _check(False, violated, not violated)
    if "expected_quantity" in expected:
        qty = po.quantity if po else 0
        checks["quantity"] = _check(expected["expected_quantity"], qty, qty == expected["expected_quantity"])
    return checks


def oracle_check(
    true_state: SimulatorState,
    expected: Dict[str, Any],
    initial_state: SimulatorState = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Args:
        true_state:    the simulator's hidden ground truth at task end.
        expected:      the task's expected_final_state dict.
        initial_state: the task's initial state (used to count new orders and to
                       check quote validity against the original quote expiry).
    Returns:
        (passed, diff) — passed is True only if every check passes.
    """
    checks = _always_on(true_state, initial_state)

    for i, req in enumerate(expected.get("orders", [])):
        checks[f"order[{i}]:{req['project_id']}/{req['component_id']}"] = _order_requirement(true_state, req)

    for po_id, status in expected.get("order_states", {}).items():
        po = true_state.orders.get(po_id)
        actual = po.status.value if po else "NOT_FOUND"
        checks[f"order_state:{po_id}"] = _check(status, actual, actual == status)

    for inv_id, status in expected.get("invoice_states", {}).items():
        inv = true_state.invoices.get(inv_id)
        actual = inv.status if inv else "NOT_FOUND"
        checks[f"invoice_state:{inv_id}"] = _check(status, actual, actual == status)

    for bud_id, amount in expected.get("budget_reserved", {}).items():
        b = true_state.budgets.get(bud_id)
        actual = round(b.reserved, 2) if b else None
        checks[f"budget_reserved:{bud_id}"] = _check(amount, actual,
                                                     actual is not None and abs(actual - amount) <= EPS)

    if "max_new_orders" in expected:
        initial_ids = set(initial_state.orders) if initial_state else set()
        new = sorted(o for o in true_state.orders if o not in initial_ids)
        checks["max_new_orders"] = _check(expected["max_new_orders"], new,
                                          len(new) <= expected["max_new_orders"])

    checks.update(_legacy(true_state, expected))

    task_specific = len(checks) > 4
    passed = task_specific and all(c["pass"] for c in checks.values())
    return passed, checks
