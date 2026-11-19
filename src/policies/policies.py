"""
policies.py — Phase 6
Verification policy router — Policies A, B, C, D, E.
This is THE core experimental variable. Only this changes between runs.
"""
import math
from typing import Tuple, Any, Dict

# High-risk tools — Policy D always verifies after these.
# Single source of truth: the risk tags in the tool registry.
from ..environment.tools import HIGH_RISK_TOOLS, MEDIUM_RISK_TOOLS
from .config import validate_policy_config

CONF_THRESHOLD = 0.6   # below this → verify (Policy D/E)


def should_verify(
    policy:     str,
    action:     Dict[str, Any],
    result:     Dict[str, Any],
    history:    list,
    step:       int,
    controller: Any = None,     # BudgetController — only for Policy E
    cache:      Any = None,     # VerdictCache — optional
    *,
    config:     Any = None,     # A–D settings; defaults preserve the existing schedule
) -> Tuple[bool, str]:
    """
    Returns: (verify: bool, reason: str)

    reason is one of:
        "no_verify"       → Policy A
        "always_verify"   → Policy B
        "fixed_schedule"  → Policy C
        "high_risk_tool"  → Policy D trigger
        "schema_fail"     → Policy D trigger
        "low_confidence"  → Policy D trigger
        "no_trigger"      → Policy D — no trigger
        "risk_score"      → Policy E
        "cache_hit"       → served from cache
    """

    settings = validate_policy_config(config)
    if type(step) is not int or step < 0:
        raise ValueError("step must be a non-negative integer")
    tool_name = action.get("tool", "")

    # ── Policy A: Never verify ─────────────────────────────────────────────────
    if policy == "A":
        return False, "no_verify"

    # ── Policy B: Always verify ────────────────────────────────────────────────
    if policy == "B":
        return True, "always_verify"

    # Zero-based agent actions: interval 3 checks actions 1, 4, 7, ...
    if policy == "C":
        if step % settings["interval"] == 0:
            return True, "fixed_schedule"
        return False, "no_trigger"

    # ── Policy D: Adaptive ────────────────────────────────────────────────────
    if policy == "D":
        # Trigger 1: high-risk tool
        if tool_name in HIGH_RISK_TOOLS:
            return True, "high_risk_tool"
        # Trigger 2: schema / sanity failure
        if _schema_fail(tool_name, result):
            return True, "schema_fail"
        # Trigger 3: the agent's confidence before observing the tool result.
        confidence = parse_confidence(action.get("confidence"))
        if confidence is not None and confidence < settings["confidence_threshold"]:
            return True, "low_confidence"
        # Check verdict cache first
        if cache:
            cached = cache.get(tool_name, action.get("args", {}), result)
            if cached is not None:
                return cached[0], "cache_hit"
        return False, "no_trigger"

    # ── Policy E: Budget-controlled adaptive ──────────────────────────────────
    if policy == "E":
        assert controller is not None, "Policy E requires a BudgetController"
        score  = _risk_score(tool_name, result, history)
        decide = score >= controller.threshold
        return decide, "risk_score"

    raise ValueError(f"Unknown policy: {policy}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_confidence(value):
    """Accept only a numeric score in [0, 1]; everything else is unavailable."""
    if type(value) not in (int, float) or not 0 <= value <= 1:
        return None
    return float(value)


# Required fields describe observations, not hidden simulator state.
_NUMBER = (int, float)
_RESULT_FIELDS = {
    "search_vendors": {"vendors": list},
    "get_vendor_details": {"id": str, "name": str, "eligible": bool,
                           "approved": bool, "preferred": bool, "payment_profile": str},
    "check_vendor_status": {"id": str, "approved": bool, "suspended": bool, "eligible": bool},
    "get_quotes": {"component_id": str, "quotes": list},
    "check_quote_validity": {"id": str, "status": str, "expired": bool,
                             "expiry_days": int, "current_step": int},
    "check_budget": {"id": str, "allocated": _NUMBER, "spent": _NUMBER,
                     "reserved": _NUMBER, "remaining": _NUMBER},
    "check_existing_orders": {"project_id": str, "orders": list},
    "compare_quotes": {"ranked_quotes": list},
    "check_invoice": {"id": str, "po_id": str, "amount": _NUMBER,
                      "po_total": (int, float, type(None)), "line_items": list,
                      "mismatch": bool, "status": str},
    "request_discount": {"success": bool},
    "request_approval": {"approval_id": str, "po_id": str, "status": str},
    "dispute_invoice": {"id": str, "status": str, "reason": str},
    "create_purchase_order": {"po_id": str, "status": str, "vendor_id": str,
                              "component_id": str, "quantity": int, "unit_price": _NUMBER,
                              "total": _NUMBER, "requires_approval": bool},
    "modify_order": {"po_id": str, "status": str, "quantity": int, "total": _NUMBER,
                     "approval_invalidated": bool, "requires_approval": bool},
    "approve_order": {"approval_id": str, "po_id": str, "status": str},
    "release_order": {"po_id": str, "status": str},
    "cancel_order": {"po_id": str, "status": str},
}
_LIST_FIELDS = {
    "vendors": {"id": str, "name": str, "preferred": bool},
    "quotes": {"id": str, "vendor_id": str, "unit_price": _NUMBER, "quantity": int,
               "shipping_cost": _NUMBER, "total_price": _NUMBER, "status": str, "expired": bool},
    "orders": {"id": str, "vendor_id": str, "component_id": str, "quantity": int,
               "unit_price": _NUMBER, "status": str, "total": _NUMBER,
               "approval_id": (str, type(None))},
    "ranked_quotes": {"id": str, "vendor_id": str, "unit_price": _NUMBER,
                      "total_price": _NUMBER, "shipping_cost": _NUMBER, "expired": bool},
}
_ORDER_STATUSES = {"DRAFT", "PENDING_APPROVAL", "APPROVED", "RELEASED", "CANCELLED"}


def _valid_result_fields(record, fields):
    """Check required observation fields before doing arithmetic or comparisons."""
    if not isinstance(record, dict):
        return False
    for name, expected in fields.items():
        if name not in record:
            return False
        value = record[name]
        allowed = expected if isinstance(expected, tuple) else (expected,)
        if type(value) not in allowed:
            return False
        if type(value) in (int, float):
            if value < 0 or (type(value) is float and not math.isfinite(value)):
                return False
        if name == "quantity" and value < 1:
            return False
        if (name == "id" or name.endswith("_id")) and value == "":
            return False
    return True


def _quote_sanity_fail(quote):
    """USED quotes can also be expired; only ACTIVE/EXPIRED constrain the flag."""
    status = quote["status"]
    if status not in {"ACTIVE", "EXPIRED", "USED"}:
        return True
    return (status == "ACTIVE" and quote["expired"]) or (status == "EXPIRED" and not quote["expired"])


def _list_sanity_fail(name, records):
    for record in records:
        if not _valid_result_fields(record, _LIST_FIELDS[name]):
            return True
        if name == "quotes":
            total = record["unit_price"] * record["quantity"] + record["shipping_cost"]
            if _quote_sanity_fail(record) or not math.isclose(
                    record["total_price"], total, rel_tol=0, abs_tol=0.01):
                return True
        if name == "orders" and record["status"] not in _ORDER_STATUSES:
            return True
    if name == "ranked_quotes":
        totals = [record["total_price"] for record in records]
        return totals != sorted(totals)
    return False


def _discount_schema_fail(result):
    if result["success"]:
        return not _valid_result_fields(result, {
            "quote_id": str, "new_unit_price": _NUMBER, "new_total_price": _NUMBER})
    if not _valid_result_fields(result, {"reason": str}):
        return True
    for name in ("unit_price", "min_unit_price"):
        if name in result and not _valid_result_fields(result, {name: _NUMBER}):
            return True
    return False


def _scalar_sanity_fail(tool_name, result):
    if tool_name == "check_budget":
        remaining = result["allocated"] - result["spent"] - result["reserved"]
        return not math.isclose(result["remaining"], remaining, rel_tol=0, abs_tol=0.01)
    if tool_name == "check_vendor_status":
        return result["approved"] and result["suspended"]
    if tool_name == "check_quote_validity":
        return (_quote_sanity_fail(result)
                or (result["current_step"] >= result["expiry_days"] and not result["expired"]))
    if tool_name == "check_invoice":
        if result["status"] not in {"unpaid", "paid", "disputed"}:
            return True
        if not all(isinstance(item, dict) for item in result["line_items"]):
            return True
        return (result["po_total"] is not None and not result["mismatch"]
                and abs(result["amount"] - result["po_total"]) > 0.01)
    expected_status = {
        "request_approval": "PENDING", "approve_order": "APPROVED",
        "create_purchase_order": "DRAFT", "modify_order": "DRAFT",
        "release_order": "RELEASED", "cancel_order": "CANCELLED",
        "dispute_invoice": "disputed",
    }
    if tool_name in expected_status:
        return result["status"] != expected_status[tool_name]
    return False


def _schema_fail(tool_name: str, result: Any) -> bool:
    """Cheap observed-only checks. Passing them does not establish true success."""
    if not isinstance(result, dict):
        return True
    if "parse_error" in result or "error" in result or result.get("timeout"):
        return True
    fields = _RESULT_FIELDS.get(tool_name)
    if fields is None or not _valid_result_fields(result, fields):
        return True
    for name in fields:
        if name in _LIST_FIELDS and _list_sanity_fail(name, result[name]):
            return True
    if tool_name == "compare_quotes" and "not_found" in result:
        missing = result["not_found"]
        if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
            return True
    if tool_name == "request_discount":
        return _discount_schema_fail(result)
    return _scalar_sanity_fail(tool_name, result)


def _risk_score(tool_name: str, result: dict, history: list) -> float:
    """
    Continuous [0.0, 1.0] risk score for Policy E.
    Higher = more likely to verify.
    """
    score = 0.0
    # Tool tier
    if tool_name in HIGH_RISK_TOOLS:
        score += 0.5
    elif tool_name in MEDIUM_RISK_TOOLS:
        score += 0.25
    # Schema fail
    if _schema_fail(tool_name, result):
        score += 0.4
    # Confidence
    confidence = result.get("_confidence", 1.0) if isinstance(result, dict) else 1.0
    score += (1.0 - confidence) * 0.2
    return min(score, 1.0)


# ─── Policy E: Budget Controller ──────────────────────────────────────────────

class BudgetController:
    """
    EWMA controller that nudges the verification threshold to hit a target rate.
    Add this after the A–D baseline is stable (Phase 10).
    """
    def __init__(self, target_rate: float = 0.25, k: float = 0.05, threshold: float = 0.5):
        self.target_rate = target_rate
        self.k           = k
        self.threshold   = threshold
        self.ewma_rate   = target_rate

    def update(self, verified_this_batch: int, total_this_batch: int):
        actual_rate    = verified_this_batch / max(total_this_batch, 1)
        self.ewma_rate = 0.8 * self.ewma_rate + 0.2 * actual_rate
        self.threshold += self.k * (self.ewma_rate - self.target_rate)
        self.threshold  = min(max(self.threshold, 0.0), 1.0)
