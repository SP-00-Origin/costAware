"""Phase 1 — simulator, tool registry and environment wrapper."""
import pytest

from src.environment.entities import POStatus, ApprovalStatus
from src.environment.env import ProcurementEnv
from src.environment.simulator import ProcurementSimulator
from src.environment.tasks import build_state, generate_procurement_task
from src.environment.tools import (
    TOOL_SPECS, HIGH_RISK_TOOLS, MEDIUM_RISK_TOOLS, READ_TOOLS, validate_args, execute_tool,
)
from tests.conftest import base_initial_state, make_task


# ─── Load / reset / determinism ──────────────────────────────────────────────

def test_reset_restores_initial_state(sim):
    sim.create_purchase_order("PROJ-A", "Q1", 10)
    sim.advance_step()
    assert sim.state.orders and sim.state.step == 1
    sim.reset()
    assert sim.state.orders == {} and sim.state.step == 0
    assert sim.state.budgets["BUD-A"].reserved == 0


def test_ids_are_sequential_and_deterministic():
    ids = []
    for _ in range(2):
        s = ProcurementSimulator()
        s.load(make_task().build_state())
        po1 = s.create_purchase_order("PROJ-A", "Q1", 10)["po_id"]
        po2 = s.create_purchase_order("PROJ-A", "Q1", 5)["po_id"]
        apr = s.request_approval(po1, "alice")["approval_id"]
        ids.append((po1, po2, apr))
    assert ids[0] == ids[1] == ("PO-0001", "PO-0002", "APR-0001")


def test_build_state_rejects_duplicate_ids():
    st = base_initial_state()
    st["vendors"].append({"id": "V1", "name": "dup"})
    with pytest.raises(ValueError):
        build_state(st)


# ─── Budget accounting ───────────────────────────────────────────────────────

def test_budget_lifecycle_create_modify_release(sim):
    b = sim.state.budgets["BUD-A"]
    r = sim.create_purchase_order("PROJ-A", "Q1", 10)          # 4800 + 200
    assert r["total"] == 5000 and b.reserved == 5000 and b.remaining == 15000
    sim.modify_order(r["po_id"], 15)                           # 7200 + 200
    assert b.reserved == 7400
    sim.release_order(r["po_id"])                              # under threshold
    assert b.reserved == 0 and b.spent == 7400 and b.remaining == 12600


def test_cancel_frees_reservation(sim):
    r = sim.create_purchase_order("PROJ-A", "Q1", 10)
    sim.cancel_order(r["po_id"])
    b = sim.state.budgets["BUD-A"]
    assert b.reserved == 0 and sim.state.orders[r["po_id"]].status == POStatus.CANCELLED
    assert "error" in sim.cancel_order(r["po_id"])            # already cancelled


def test_budget_overrun_is_allowed_but_visible():
    s = ProcurementSimulator()
    s.load(make_task(base_initial_state(allocated=3000)).build_state())
    r = s.create_purchase_order("PROJ-A", "Q1", 10)            # 5000 > 3000
    assert "po_id" in r
    assert s.state.budgets["BUD-A"].remaining < 0             # oracle will fail this


# ─── Approval workflow ───────────────────────────────────────────────────────

def _approval_sim():
    s = ProcurementSimulator()
    s.load(make_task(base_initial_state(threshold=1000)).build_state())
    return s


def test_full_approval_flow():
    s = _approval_sim()
    po = s.create_purchase_order("PROJ-A", "Q1", 10)["po_id"]
    assert "error" in s.release_order(po)                      # needs approval
    apr = s.request_approval(po, "alice")["approval_id"]
    assert s.state.orders[po].status == POStatus.PENDING
    assert s.approve_order(apr)["status"] == "APPROVED"
    assert s.release_order(po)["status"] == "RELEASED"


def test_requester_must_be_owner():
    s = _approval_sim()
    po = s.create_purchase_order("PROJ-A", "Q1", 10)["po_id"]
    assert "error" in s.request_approval(po, "mallory")


def test_modify_invalidates_approval_even_after_approved():
    s = _approval_sim()
    po = s.create_purchase_order("PROJ-A", "Q1", 10)["po_id"]
    apr = s.request_approval(po, "alice")["approval_id"]
    s.approve_order(apr)
    r = s.modify_order(po, 12)
    assert r["approval_invalidated"] is True
    assert s.state.approvals[apr].status == ApprovalStatus.INVALIDATED
    assert s.state.orders[po].status == POStatus.DRAFT
    assert "error" in s.approve_order(apr)                     # stale approval unusable
    assert "error" in s.release_order(po)
    apr2 = s.request_approval(po, "alice")["approval_id"]
    s.approve_order(apr2)
    assert s.release_order(po)["status"] == "RELEASED"


def test_release_under_threshold_needs_no_approval(sim):
    po = sim.create_purchase_order("PROJ-A", "Q1", 10)["po_id"]   # 5000 ≤ 10000
    assert sim.release_order(po)["status"] == "RELEASED"
    assert "error" in sim.cancel_order(po)                    # released is final


# ─── Quotes, discounts, invoices ─────────────────────────────────────────────

def test_quote_expiry_follows_clock(sim):
    assert sim.check_quote_validity("Q3")["expired"] is False
    for _ in range(3):
        sim.advance_step()
    v = sim.check_quote_validity("Q3")
    assert v["expired"] is True and v["status"] == "EXPIRED"
    statuses = {q["id"]: q["status"] for q in sim.get_quotes("C-A")["quotes"]}
    assert statuses == {"Q1": "ACTIVE", "Q2": "ACTIVE", "Q3": "EXPIRED"}


def test_discount_floor_and_single_use(sim):
    assert sim.request_discount("Q1", 400.0)["success"] is False   # below 90% (432)
    r = sim.request_discount("Q1", 440.0)
    assert r["success"] is True and sim.state.quotes["Q1"].unit_price == 440.0
    assert sim.request_discount("Q1", 430.0)["success"] is False   # already used
    po = sim.create_purchase_order("PROJ-A", "Q1", 10)
    assert po["unit_price"] == 440.0


def test_policy_violations_go_through(sim):
    """Suspended vendor / expired quote orders are accepted; the oracle judges them."""
    assert "po_id" in sim.create_purchase_order("PROJ-A", "Q2", 10)   # suspended vendor
    for _ in range(5):
        sim.advance_step()
    assert "po_id" in sim.create_purchase_order("PROJ-A", "Q3", 10)   # expired quote


def test_integrity_errors(sim):
    assert "error" in sim.create_purchase_order("PROJ-X", "Q1", 1)
    assert "error" in sim.create_purchase_order("PROJ-A", "Q9", 1)
    assert "error" in sim.create_purchase_order("PROJ-A", "Q1", 0)
    assert "error" in sim.create_purchase_order("PROJ-A", "Q1", 999)   # more than quoted
    assert "error" in sim.check_budget("NOPE")
    assert "error" in sim.get_quotes("C-NOPE")


def test_invoice_mismatch_and_dispute():
    st = base_initial_state()
    st["orders"] = [{"id": "PO-EX1", "vendor_id": "V1", "component_id": "C-A", "quantity": 10,
                     "unit_price": 480.0, "shipping_cost": 200.0, "project_id": "PROJ-A",
                     "status": "RELEASED", "released": True}]
    st["invoices"] = [{"id": "INV-1", "po_id": "PO-EX1", "amount": 5000.0},
                      {"id": "INV-2", "po_id": "PO-EX1", "amount": 5600.0}]
    s = ProcurementSimulator()
    s.load(build_state(st))
    assert s.check_invoice("INV-1")["mismatch"] is False
    assert s.check_invoice("INV-2")["mismatch"] is True
    assert s.dispute_invoice("INV-2", "amount")["status"] == "disputed"


# ─── Tool registry ───────────────────────────────────────────────────────────

def test_registry_matches_simulator():
    assert len(TOOL_SPECS) == 17
    for name in TOOL_SPECS:
        assert callable(getattr(ProcurementSimulator, name, None)), name
    assert HIGH_RISK_TOOLS == {"create_purchase_order", "modify_order", "approve_order",
                               "release_order", "cancel_order"}
    assert MEDIUM_RISK_TOOLS == {"request_discount", "request_approval", "dispute_invoice"}
    assert len(READ_TOOLS) == 9


def test_validate_args():
    assert validate_args("create_purchase_order",
                         {"project_id": "P", "quote_id": "Q", "quantity": "10"}) == (
        {"project_id": "P", "quote_id": "Q", "quantity": 10}, "")
    assert validate_args("nope", {})[1].startswith("Unknown tool")
    assert "Missing" in validate_args("check_budget", {})[1]
    assert "Unknown argument" in validate_args("check_budget", {"budget_id": "B", "x": 1})[1]
    assert "integer" in validate_args("modify_order", {"po_id": "P", "quantity": 2.5})[1]
    assert validate_args("dispute_invoice", {"invoice_id": "I"})[1] == ""   # reason optional


def test_execute_tool_reports_bad_args_as_error(sim):
    assert "error" in execute_tool(sim, "check_budget", {"bad": 1})


# ─── Environment wrapper ─────────────────────────────────────────────────────

def test_env_records_and_advances_clock():
    env = ProcurementEnv(make_task())
    r1 = env.call("check_budget", {"budget_id": "BUD-A"})
    r2 = env.call("not_a_tool", {})
    assert (r1["step"], r2["step"]) == (0, 1) and env.true_state.step == 2
    assert r1["true_result"] == r1["observed_result"] and r1["fault_injected"] is None
    assert r2["invalid_call"] is True and "error" in r2["observed_result"]
    assert r1["risk"] == "low"
    env.reset()
    assert env.records == [] and env.true_state.step == 0


# ─── Initial-state generator ─────────────────────────────────────────────────

def test_generator_is_deterministic():
    a = generate_procurement_task(7)
    b = generate_procurement_task(7)
    assert a.model_dump() == b.model_dump()
    assert generate_procurement_task(8).model_dump() != a.model_dump()
