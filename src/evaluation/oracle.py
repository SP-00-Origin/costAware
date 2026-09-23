"""
oracle.py — Phase 2
The Deterministic Oracle. NEVER uses an LLM.
Compares the simulator's true final state against the task's expected_final_state.
Returns PASS/FAIL + a structured diff.
"""
from typing import Any, Dict, Tuple
from ..environment.state import SimulatorState
from ..environment.entities import POStatus, ApprovalStatus


def oracle_check(
    true_state: SimulatorState,
    expected: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """
    Args:
        true_state: The simulator's hidden ground truth at task end.
        expected:   The task definition's expected_final_state dict.

    Returns:
        (passed: bool, diff: dict)
    """
    checks = {}

    # ── PO must reach expected final status ───────────────────────────────────
    if "po_status" in expected:
        po_id = expected.get("po_id")
        po    = true_state.orders.get(po_id)
        actual_status = po.status.value if po else "NOT_CREATED"
        checks["po_status"] = {
            "expected": expected["po_status"],
            "actual":   actual_status,
            "pass":     actual_status == expected["po_status"]
        }

    # ── Vendor must be eligible (not suspended) ───────────────────────────────
    if "vendor_id" in expected:
        vid    = expected["vendor_id"]
        vendor = true_state.vendors.get(vid)
        checks["vendor_eligible"] = {
            "expected": True,
            "actual":   bool(vendor and vendor.eligible and not vendor.suspended),
            "pass":     bool(vendor and vendor.eligible and not vendor.suspended)
        }

    # ── Budget must not be exceeded ───────────────────────────────────────────
    if "budget_id" in expected:
        bid    = expected["budget_id"]
        budget = true_state.budgets.get(bid)
        within = budget.remaining >= 0 if budget else False
        checks["budget_not_exceeded"] = {
            "expected": True,
            "actual":   within,
            "pass":     within
        }

    # ── Approval must be valid if required ────────────────────────────────────
    if expected.get("approval_required"):
        po_id  = expected.get("po_id")
        po     = true_state.orders.get(po_id)
        apr_id = po.approval_id if po else None
        apr    = true_state.approvals.get(apr_id) if apr_id else None
        valid  = bool(apr and apr.status == ApprovalStatus.APPROVED and apr.valid)
        checks["approval_valid"] = {
            "expected": True,
            "actual":   valid,
            "pass":     valid
        }

    # ── No suspended vendor used in any order ────────────────────────────────
    if expected.get("no_suspended_vendor"):
        violated = any(
            true_state.vendors.get(o.vendor_id, None) and
            true_state.vendors[o.vendor_id].suspended
            for o in true_state.orders.values()
        )
        checks["no_suspended_vendor"] = {
            "expected": False,
            "actual":   violated,
            "pass":     not violated
        }

    # ── Quantity check ────────────────────────────────────────────────────────
    if "expected_quantity" in expected:
        po_id = expected.get("po_id")
        po    = true_state.orders.get(po_id)
        actual_qty = po.quantity if po else 0
        checks["quantity"] = {
            "expected": expected["expected_quantity"],
            "actual":   actual_qty,
            "pass":     actual_qty == expected["expected_quantity"]
        }

    # ── Final verdict ─────────────────────────────────────────────────────────
    passed = all(c["pass"] for c in checks.values()) if checks else False

    return passed, checks
