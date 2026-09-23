"""
policies.py — Phase 6
Verification policy router — Policies A, B, C, D, E.
This is THE core experimental variable. Only this changes between runs.
"""
from typing import Tuple, Any, Dict, Optional

# High-risk tools — Policy D always verifies after these
HIGH_RISK_TOOLS = {
    "create_purchase_order",
    "modify_order",
    "approve_order",
    "release_order",
    "cancel_order",
}

CONF_THRESHOLD = 0.6   # below this → verify (Policy D/E)


def should_verify(
    policy:     str,
    action:     Dict[str, Any],
    result:     Dict[str, Any],
    history:    list,
    step:       int,
    controller: Any = None,     # BudgetController — only for Policy E
    cache:      Any = None,     # VerdictCache — optional
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

    tool_name = action.get("tool", "")

    # ── Policy A: Never verify ─────────────────────────────────────────────────
    if policy == "A":
        return False, "no_verify"

    # ── Policy B: Always verify ────────────────────────────────────────────────
    if policy == "B":
        return True, "always_verify"

    # ── Policy C: Fixed schedule (every 3 steps) ───────────────────────────────
    if policy == "C":
        if step % 3 == 0:
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
        # Trigger 3: low confidence (if available in result metadata)
        confidence = result.get("_confidence", 1.0)
        if confidence < CONF_THRESHOLD:
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

def _schema_fail(tool_name: str, result: dict) -> bool:
    """Deterministic schema / sanity check — never calls an LLM."""
    if not isinstance(result, dict):
        return True
    if "parse_error" in result:
        return True
    if "error" in result:
        return True   # tool returned an error — always verify
    # Tool-specific checks
    if tool_name == "check_budget":
        required = {"allocated", "spent", "reserved", "remaining"}
        if not required.issubset(result.keys()):
            return True
        if result.get("remaining", 0) < 0:
            return True   # negative budget is suspicious
    if tool_name == "check_vendor_status":
        if result.get("approved") and result.get("suspended"):
            return True   # contradictory — approved AND suspended
    if tool_name == "create_purchase_order":
        if "po_id" not in result and "error" not in result:
            return True
    return False


def _risk_score(tool_name: str, result: dict, history: list) -> float:
    """
    Continuous [0.0, 1.0] risk score for Policy E.
    Higher = more likely to verify.
    """
    score = 0.0
    # Tool tier
    if tool_name in HIGH_RISK_TOOLS:
        score += 0.5
    elif tool_name in {"request_discount", "request_approval"}:
        score += 0.25
    # Schema fail
    if _schema_fail(tool_name, result):
        score += 0.4
    # Confidence
    confidence = result.get("_confidence", 1.0)
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
