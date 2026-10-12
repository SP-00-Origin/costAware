"""
tools.py — Phase 1
Tool registry: the single source of truth for every tool the agent can call.

Each entry carries
  - risk:        "low" | "medium" | "high"  (Policy D uses this as a real signal)
  - description: shown to the LLM
  - parameters:  JSON schema, used both for LLM tool-calling and for argument validation

Tool names map 1:1 to methods on ProcurementSimulator.
"""
from typing import Any, Dict, Tuple

RISK_LOW, RISK_MEDIUM, RISK_HIGH = "low", "medium", "high"


def _obj(props: Dict[str, Any], required=None) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(required or props.keys())}


_STR = {"type": "string"}
_INT = {"type": "integer", "minimum": 1}
_NUM = {"type": "number"}

TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    # ── Low risk / read ───────────────────────────────────────────────────────
    "search_vendors": {
        "risk": RISK_LOW,
        "description": "List all known vendors (id, name, preferred flag).",
        "parameters": _obj({}),
    },
    "get_vendor_details": {
        "risk": RISK_LOW,
        "description": "Vendor profile: eligibility, approval, preferred flag, payment profile.",
        "parameters": _obj({"vendor_id": _STR}),
    },
    "check_vendor_status": {
        "risk": RISK_LOW,
        "description": "Current vendor standing: approved, suspended, eligible.",
        "parameters": _obj({"vendor_id": _STR}),
    },
    "get_quotes": {
        "risk": RISK_LOW,
        "description": "All supplier quotes for a component, with prices, shipping, quantity and expiry status.",
        "parameters": _obj({"component_id": _STR}),
    },
    "check_quote_validity": {
        "risk": RISK_LOW,
        "description": "Whether a quote is still valid (not expired) at the current step.",
        "parameters": _obj({"quote_id": _STR}),
    },
    "check_budget": {
        "risk": RISK_LOW,
        "description": "Budget allocated, spent, reserved and remaining.",
        "parameters": _obj({"budget_id": _STR}),
    },
    "check_existing_orders": {
        "risk": RISK_LOW,
        "description": "All purchase orders for a project, with status, quantity and approval id.",
        "parameters": _obj({"project_id": _STR}),
    },
    "compare_quotes": {
        "risk": RISK_LOW,
        "description": "Rank the given quotes by total price including shipping (cheapest first).",
        "parameters": _obj({"quote_ids": {"type": "array", "items": _STR}}),
    },
    "check_invoice": {
        "risk": RISK_LOW,
        "description": "Inspect an invoice and whether its amount matches the PO total.",
        "parameters": _obj({"invoice_id": _STR}),
    },
    # ── Medium risk / write ───────────────────────────────────────────────────
    "request_discount": {
        "risk": RISK_MEDIUM,
        "description": "Ask the vendor for a lower unit price on a quote. Vendors accept at most a 10% "
                       "reduction, and each quote can be renegotiated only once.",
        "parameters": _obj({"quote_id": _STR, "requested_price": _NUM}),
    },
    "request_approval": {
        "risk": RISK_MEDIUM,
        "description": "Submit a DRAFT purchase order for manager approval. The requester must be the project owner.",
        "parameters": _obj({"po_id": _STR, "requester": _STR}),
    },
    "dispute_invoice": {
        "risk": RISK_MEDIUM,
        "description": "Mark an invoice as disputed (e.g. amount does not match the PO).",
        "parameters": _obj({"invoice_id": _STR, "reason": _STR}, required=["invoice_id"]),
    },
    # ── High risk / state-changing ────────────────────────────────────────────
    "create_purchase_order": {
        "risk": RISK_HIGH,
        "description": "Create a DRAFT purchase order from a supplier quote and reserve budget.",
        "parameters": _obj({"project_id": _STR, "quote_id": _STR, "quantity": _INT}),
    },
    "modify_order": {
        "risk": RISK_HIGH,
        "description": "Change the quantity of a non-released PO. Invalidates any existing approval "
                       "and returns the PO to DRAFT.",
        "parameters": _obj({"po_id": _STR, "quantity": _INT}),
    },
    "approve_order": {
        "risk": RISK_HIGH,
        "description": "Approve a pending approval request, moving the PO to APPROVED.",
        "parameters": _obj({"approval_id": _STR}),
    },
    "release_order": {
        "risk": RISK_HIGH,
        "description": "Release a PO to the vendor. POs above the project's approval threshold must be "
                       "APPROVED first. Spends the reserved budget.",
        "parameters": _obj({"po_id": _STR}),
    },
    "cancel_order": {
        "risk": RISK_HIGH,
        "description": "Cancel a non-released PO and free its reserved budget.",
        "parameters": _obj({"po_id": _STR}),
    },
}

TOOL_NAMES      = list(TOOL_SPECS.keys())
HIGH_RISK_TOOLS = {n for n, s in TOOL_SPECS.items() if s["risk"] == RISK_HIGH}
MEDIUM_RISK_TOOLS = {n for n, s in TOOL_SPECS.items() if s["risk"] == RISK_MEDIUM}
READ_TOOLS      = {n for n, s in TOOL_SPECS.items() if s["risk"] == RISK_LOW}


def tool_risk(name: str) -> str:
    return TOOL_SPECS.get(name, {}).get("risk", RISK_LOW)


def validate_args(name: str, args: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Check tool name and arguments against the registry.
    Returns (clean_args, error). error is "" when valid.
    Integers given as whole floats/strings ("10", 10.0) are coerced — LLMs do this often.
    """
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return {}, f"Unknown tool '{name}'"
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return {}, "Tool arguments must be an object"
    schema   = spec["parameters"]
    props    = schema["properties"]
    unknown  = set(args) - set(props)
    if unknown:
        return {}, f"Unknown argument(s) for {name}: {sorted(unknown)}"
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        return {}, f"Missing argument(s) for {name}: {missing}"

    clean = {}
    for k, v in args.items():
        t = props[k]["type"]
        try:
            if t == "integer":
                if isinstance(v, bool):
                    raise ValueError
                fv = float(v)
                if fv != int(fv):
                    raise ValueError
                v = int(fv)
            elif t == "number":
                if isinstance(v, bool):
                    raise ValueError
                v = float(v)
            elif t == "string":
                if not isinstance(v, str):
                    raise ValueError
            elif t == "array":
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise ValueError
        except (TypeError, ValueError):
            return {}, f"Argument '{k}' of {name} must be of type {t}"
        clean[k] = v
    return clean, ""


def execute_tool(sim, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and run a tool on the simulator. Returns the CLEAN result."""
    clean, err = validate_args(name, args)
    if err:
        return {"error": err}
    return getattr(sim, name)(**clean)
