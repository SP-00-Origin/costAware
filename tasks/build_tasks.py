"""
build_tasks.py — Phase 2
Source of truth for the hand-written task dataset. Regenerate tasks.jsonl with:

    python tasks/build_tasks.py

Then validate (reference PASS, sabotaged trajectories FAIL):

    python scripts/validate_tasks.py

20 tasks across the 10 task families of the plan (Section 9) and three tiers:
  easy   ≤ 5 reference actions   (validate simulator/oracle)
  medium 6–9 reference actions   (branching + single traps)
  hard   ≥ 10 reference actions  (long-horizon, multi-objective)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "tasks.jsonl"
ACTIVE = {"DRAFT", "PENDING_APPROVAL", "APPROVED"}


# ─── Entity helpers ──────────────────────────────────────────────────────────

def V(id, name, approved=True, suspended=False, eligible=True, preferred=False, payment="net30"):
    return {"id": id, "name": name, "approved": approved, "suspended": suspended,
            "eligible": eligible, "preferred": preferred, "payment_profile": payment}


def C(id, name, ref_price, qty, category="hardware"):
    return {"id": id, "name": name, "category": category, "reference_price": ref_price,
            "required_qty": qty, "available_qty": qty * 4}


def Q(id, vendor, comp, price, qty, ship=0.0, expiry=100):
    return {"id": id, "vendor_id": vendor, "component_id": comp, "unit_price": float(price),
            "quantity": qty, "shipping_cost": float(ship), "expiry_days": expiry}


def P(id, name, owner, budget, threshold):
    return {"id": id, "name": name, "owner": owner, "budget_id": budget,
            "procurement_rules": {"require_approval_above": threshold}}


def PO(id, vendor, comp, qty, price, project, status, ship=0.0, approval_id=None):
    return {"id": id, "vendor_id": vendor, "component_id": comp, "quantity": qty,
            "unit_price": float(price), "shipping_cost": float(ship), "project_id": project,
            "status": status, "approval_id": approval_id, "released": status == "RELEASED"}


def APR(id, po, requester, status="APPROVED"):
    return {"id": id, "po_id": po, "requester": requester, "approver": "manager",
            "level": "manager", "status": status, "valid": True}


def INV(id, po, amount):
    return {"id": id, "po_id": po, "amount": float(amount), "status": "unpaid"}


def A(tool, **args):
    return {"tool": tool, "args": args}


def world(vendors, components, quotes, projects, budgets, orders=(), approvals=(), invoices=()):
    """Assemble an initial state; budget reserved/spent are derived from the orders so
    the starting books are always consistent."""
    proj_budget = {p["id"]: p["budget_id"] for p in projects}
    for b in budgets:
        b.setdefault("spent", 0.0)
        b["reserved"] = 0.0
    by_id = {b["id"]: b for b in budgets}
    for o in orders:
        total = o["unit_price"] * o["quantity"] + o["shipping_cost"]
        b = by_id[proj_budget[o["project_id"]]]
        if o["status"] in ACTIVE:
            b["reserved"] += total
        elif o["status"] == "RELEASED":
            b["spent"] += total
    return {"vendors": list(vendors), "components": list(components), "quotes": list(quotes),
            "projects": list(projects), "budgets": list(budgets), "orders": list(orders),
            "approvals": list(approvals), "invoices": list(invoices)}


def B(id, allocated, extra_spent=0.0):
    return {"id": id, "allocated": float(allocated), "spent": float(extra_spent)}


def rules(project, owner, budget, threshold):
    return (f"Project {project} is owned by {owner} and funded by budget {budget}. "
            f"Orders with a total above {threshold:,} require manager approval (requested by {owner}) "
            f"before release. Only use vendors that are approved and not suspended, never exceed the "
            f"budget, never order from an expired quote, and never create duplicate orders.")


def task(id, family, tier, goal, state, expected, ref, negatives=()):
    return {"id": id, "family": family, "tier": tier, "goal": goal, "initial_state": state,
            "expected_final_state": expected, "reference_solution": ref,
            "negatives": [{"name": n, "trajectory": t} for n, t in negatives]}


def order(project, comp, **kw):
    return {"project_id": project, "component_id": comp, **kw}


TASKS = []

# ═══ EASY ════════════════════════════════════════════════════════════════════

ref = [A("get_quotes", component_id="C-A"), A("check_vendor_status", vendor_id="V1"),
       A("check_budget", budget_id="BUD-A"),
       A("create_purchase_order", project_id="PROJ-A", quote_id="Q1", quantity=10),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T01", "new_procurement", "easy",
    "Buy 10 units of component C-A (Circuit Board Alpha) for project PROJ-A and release the order. "
    + rules("PROJ-A", "alice", "BUD-A", 10000),
    world([V("V1", "TechParts Ltd")], [C("C-A", "Circuit Board Alpha", 500, 10)],
          [Q("Q1", "V1", "C-A", 480, 20, ship=200)],
          [P("PROJ-A", "Project Alpha", "alice", "BUD-A", 10000)], [B("BUD-A", 20000)]),
    {"orders": [order("PROJ-A", "C-A", vendor_id="V1", quantity=10, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("not_released", ref[:-1])]))

ref = [A("check_existing_orders", project_id="PROJ-B"), A("get_quotes", component_id="C-D"),
       A("check_vendor_status", vendor_id="V2"),
       A("create_purchase_order", project_id="PROJ-B", quote_id="QD1", quantity=10),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T02", "duplicate_prevention", "easy",
    "Project PROJ-B needs 20 units of component C-B and 10 units of component C-D. Some of this may "
    "already be on order: check existing orders first and only order what is missing, then release it. "
    + rules("PROJ-B", "bob", "BUD-B", 10000),
    world([V("V1", "CableCo"), V("V2", "SensorWorks")],
          [C("C-B", "Shielded Cable", 100, 20), C("C-D", "Pressure Sensor", 300, 10)],
          [Q("QB1", "V1", "C-B", 95, 50), Q("QD1", "V2", "C-D", 300, 10, ship=50)],
          [P("PROJ-B", "Project Beta", "bob", "BUD-B", 10000)], [B("BUD-B", 30000)],
          orders=[PO("PO-EX1", "V1", "C-B", 20, 100, "PROJ-B", "RELEASED")]),
    {"orders": [order("PROJ-B", "C-B", quantity=20, status="RELEASED"),
                order("PROJ-B", "C-D", vendor_id="V2", quantity=10, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("duplicate_C-B", ref + [A("create_purchase_order", project_id="PROJ-B", quote_id="QB1",
                                     quantity=20), A("release_order", po_id="PO-0002")])]))

ref = [A("check_existing_orders", project_id="PROJ-C"), A("release_order", po_id="PO-EX2")]
TASKS.append(task(
    "T03", "approval_workflow", "easy",
    "Order PO-EX2 for project PROJ-C has already been approved by the manager. Release it to the "
    "vendor. Do not create any new orders. " + rules("PROJ-C", "carol", "BUD-C", 5000),
    world([V("V1", "MetalWorks")], [C("C-E", "Steel Bracket", 400, 30)],
          [Q("QE1", "V1", "C-E", 400, 40)],
          [P("PROJ-C", "Project Gamma", "carol", "BUD-C", 5000)], [B("BUD-C", 50000)],
          orders=[PO("PO-EX2", "V1", "C-E", 30, 400, "PROJ-C", "APPROVED", approval_id="APR-EX2")],
          approvals=[APR("APR-EX2", "PO-EX2", "carol")]),
    {"orders": [order("PROJ-C", "C-E", quantity=30, status="RELEASED", approval_valid=True)],
     "budget_reserved": {"BUD-C": 0.0}, "max_new_orders": 0},
    ref, [("modified_before_release", [ref[0], A("modify_order", po_id="PO-EX2", quantity=31),
                                       A("release_order", po_id="PO-EX2")])]))

ref = [A("check_existing_orders", project_id="PROJ-D"), A("cancel_order", po_id="PO-EX3"),
       A("check_budget", budget_id="BUD-D")]
TASKS.append(task(
    "T04", "po_cancellation", "easy",
    "Project PROJ-D no longer needs component C-F. Cancel its open order for C-F, leave every other "
    "order untouched, and confirm the budget reservation was freed. "
    + rules("PROJ-D", "dev", "BUD-D", 10000),
    world([V("V1", "Fasteners Inc")], [C("C-F", "Hex Bolt Kit", 600, 8), C("C-G", "Washer Pack", 200, 5)],
          [Q("QF1", "V1", "C-F", 600, 10), Q("QG1", "V1", "C-G", 200, 10)],
          [P("PROJ-D", "Project Delta", "dev", "BUD-D", 10000)], [B("BUD-D", 20000)],
          orders=[PO("PO-EX3", "V1", "C-F", 8, 600, "PROJ-D", "DRAFT"),
                  PO("PO-EX4", "V1", "C-G", 5, 200, "PROJ-D", "RELEASED")]),
    {"order_states": {"PO-EX3": "CANCELLED", "PO-EX4": "RELEASED"},
     "budget_reserved": {"BUD-D": 0.0}, "max_new_orders": 0},
    ref, [("nothing_done", [ref[0]])]))

ref = [A("check_invoice", invoice_id="INV-1"), A("check_invoice", invoice_id="INV-2"),
       A("dispute_invoice", invoice_id="INV-2", reason="Amount does not match PO total")]
TASKS.append(task(
    "T05", "invoice_mismatch", "easy",
    "Check invoices INV-1 and INV-2 for project PROJ-E against their purchase orders. Dispute any "
    "invoice whose amount does not match its PO total, and leave correct invoices untouched. "
    + rules("PROJ-E", "erin", "BUD-E", 10000),
    world([V("V1", "OptiParts")], [C("C-H", "Lens Module", 250, 10), C("C-I", "Laser Diode", 1000, 4)],
          [], [P("PROJ-E", "Project Echo", "erin", "BUD-E", 10000)], [B("BUD-E", 20000)],
          orders=[PO("PO-EX5", "V1", "C-H", 10, 250, "PROJ-E", "RELEASED", ship=100),
                  PO("PO-EX6", "V1", "C-I", 4, 1000, "PROJ-E", "RELEASED")],
          invoices=[INV("INV-1", "PO-EX5", 2600), INV("INV-2", "PO-EX6", 4400)]),
    {"invoice_states": {"INV-1": "unpaid", "INV-2": "disputed"}, "max_new_orders": 0},
    ref, [("disputed_both", ref + [A("dispute_invoice", invoice_id="INV-1", reason="x")])]))

ref = [A("check_existing_orders", project_id="PROJ-M"),
       A("request_approval", po_id="PO-EX8", requester="mona"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-EX8")]
TASKS.append(task(
    "T13", "duplicate_prevention", "easy",
    "Project PROJ-M needs 15 units of component C-Q released to the vendor. An order may already "
    "exist: reuse it instead of creating a new one, get it approved, and release it. "
    + rules("PROJ-M", "mona", "BUD-M", 10000),
    world([V("V1", "Motors Direct")], [C("C-Q", "Servo Motor", 1200, 15)],
          [Q("QQ1", "V1", "C-Q", 1180, 30)],
          [P("PROJ-M", "Project Mu", "mona", "BUD-M", 10000)], [B("BUD-M", 60000)],
          orders=[PO("PO-EX8", "V1", "C-Q", 15, 1200, "PROJ-M", "DRAFT")]),
    {"orders": [order("PROJ-M", "C-Q", quantity=15, status="RELEASED", approval_valid=True)],
     "max_new_orders": 0},
    ref, [("new_order_instead", [A("create_purchase_order", project_id="PROJ-M", quote_id="QQ1", quantity=15),
                                 A("request_approval", po_id="PO-0001", requester="mona"),
                                 A("approve_order", approval_id="APR-0001"),
                                 A("release_order", po_id="PO-0001")])]))

ref = [A("check_existing_orders", project_id="PROJ-O"), A("release_order", po_id="PO-EX10"),
       A("check_invoice", invoice_id="INV-3"),
       A("dispute_invoice", invoice_id="INV-3", reason="Amount does not match PO total")]
TASKS.append(task(
    "T15", "invoice_mismatch", "easy",
    "For project PROJ-O: (1) release order PO-EX10, which has already been approved; (2) check "
    "invoice INV-3 against its purchase order and dispute it if the amount does not match. "
    + rules("PROJ-O", "omar", "BUD-O", 10000),
    world([V("V1", "PolyMaterials")], [C("C-S", "Polymer Sheet", 300, 50), C("C-T", "Heat Sink", 800, 10)],
          [], [P("PROJ-O", "Project Omicron", "omar", "BUD-O", 10000)], [B("BUD-O", 50000)],
          orders=[PO("PO-EX10", "V1", "C-S", 50, 300, "PROJ-O", "APPROVED", approval_id="APR-EX10"),
                  PO("PO-EX11", "V1", "C-T", 10, 800, "PROJ-O", "RELEASED")],
          approvals=[APR("APR-EX10", "PO-EX10", "omar")],
          invoices=[INV("INV-3", "PO-EX11", 8800)]),
    {"orders": [order("PROJ-O", "C-S", quantity=50, status="RELEASED", approval_valid=True)],
     "invoice_states": {"INV-3": "disputed"}, "max_new_orders": 0},
    ref, [("invoice_ignored", ref[:2])]))

# ═══ MEDIUM ══════════════════════════════════════════════════════════════════

ref = [A("check_existing_orders", project_id="PROJ-F"), A("get_quotes", component_id="C-J"),
       A("compare_quotes", quote_ids=["QJ1", "QJ2"]), A("check_vendor_status", vendor_id="V1"),
       A("check_budget", budget_id="BUD-F"),
       A("create_purchase_order", project_id="PROJ-F", quote_id="QJ1", quantity=12),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T06", "duplicate_prevention", "medium",
    "Project PROJ-F needs 12 units of component C-J. Check existing orders first. If there is no "
    "active order for C-J, buy the 12 units using the cheapest valid quote (lowest total including "
    "shipping) and release the order. " + rules("PROJ-F", "frank", "BUD-F", 10000),
    world([V("V1", "Valve Supply"), V("V2", "FlowTech")], [C("C-J", "Ball Valve", 350, 12)],
          [Q("QJ1", "V1", "C-J", 350, 20, ship=100), Q("QJ2", "V2", "C-J", 380, 20)],
          [P("PROJ-F", "Project Foxtrot", "frank", "BUD-F", 10000)], [B("BUD-F", 15000)],
          orders=[PO("PO-EX7", "V2", "C-J", 12, 380, "PROJ-F", "CANCELLED")]),
    {"orders": [order("PROJ-F", "C-J", vendor_id="V1", quantity=12, status="RELEASED")],
     "order_states": {"PO-EX7": "CANCELLED"}, "max_new_orders": 1},
    ref, [("trusted_cancelled_order", ref[:1])]))

ref = [A("get_quotes", component_id="C-K"), A("check_vendor_status", vendor_id="V1"),
       A("check_budget", budget_id="BUD-G"),
       A("create_purchase_order", project_id="PROJ-G", quote_id="QK1", quantity=10),
       A("request_approval", po_id="PO-0001", requester="grace"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T07", "approval_workflow", "medium",
    "Buy 10 units of component C-K (Industrial Controller) for project PROJ-G and release the order. "
    + rules("PROJ-G", "grace", "BUD-G", 10000),
    world([V("V1", "ControlSys")], [C("C-K", "Industrial Controller", 1500, 10)],
          [Q("QK1", "V1", "C-K", 1500, 15, ship=300)],
          [P("PROJ-G", "Project Golf", "grace", "BUD-G", 10000)], [B("BUD-G", 40000)]),
    {"orders": [order("PROJ-G", "C-K", vendor_id="V1", quantity=10, status="RELEASED",
                      approval_valid=True)], "max_new_orders": 1},
    ref, [("skipped_approval", ref[:4] + [ref[6]])]))

ref = [A("get_quotes", component_id="C-L"), A("check_vendor_status", vendor_id="V2"),
       A("check_vendor_status", vendor_id="V1"), A("check_budget", budget_id="BUD-H"),
       A("create_purchase_order", project_id="PROJ-H", quote_id="QL1", quantity=40),
       A("request_approval", po_id="PO-0001", requester="hiro"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T08", "vendor_status", "medium",
    "Buy 40 units of component C-L (Gasket Set) for project PROJ-H from the cheapest valid quote and "
    "release the order. " + rules("PROJ-H", "hiro", "BUD-H", 5000),
    world([V("V1", "SealPro"), V("V2", "CheapSeals", approved=False, suspended=True)],
          [C("C-L", "Gasket Set", 200, 40)],
          [Q("QL1", "V1", "C-L", 220, 40, ship=150), Q("QL2", "V2", "C-L", 190, 40)],
          [P("PROJ-H", "Project Hotel", "hiro", "BUD-H", 5000)], [B("BUD-H", 30000)]),
    {"orders": [order("PROJ-H", "C-L", vendor_id="V1", quantity=40, status="RELEASED",
                      approval_valid=True)], "max_new_orders": 1},
    ref, [("suspended_vendor", [ref[0], A("create_purchase_order", project_id="PROJ-H", quote_id="QL2",
                                          quantity=40),
                                A("request_approval", po_id="PO-0001", requester="hiro"),
                                A("approve_order", approval_id="APR-0001"),
                                A("release_order", po_id="PO-0001")])]))

ref = [A("get_quotes", component_id="C-M"), A("compare_quotes", quote_ids=["QM1", "QM2"]),
       A("check_vendor_status", vendor_id="V2"), A("check_budget", budget_id="BUD-I"),
       A("create_purchase_order", project_id="PROJ-I", quote_id="QM2", quantity=25),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T09", "budget_constraint", "medium",
    "Buy 25 units of component C-M (Cooling Fan) for project PROJ-I and release the order. Choose the "
    "quote with the lowest total cost including shipping. " + rules("PROJ-I", "ivan", "BUD-I", 10000),
    world([V("V1", "AirMove"), V("V2", "BreezeParts")], [C("C-M", "Cooling Fan", 310, 25)],
          [Q("QM1", "V1", "C-M", 300, 30, ship=1200), Q("QM2", "V2", "C-M", 320, 30)],
          [P("PROJ-I", "Project India", "ivan", "BUD-I", 10000)], [B("BUD-I", 12000)]),
    {"orders": [order("PROJ-I", "C-M", vendor_id="V2", quantity=25, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("ignored_shipping", [ref[0], A("create_purchase_order", project_id="PROJ-I", quote_id="QM1",
                                          quantity=25), A("release_order", po_id="PO-0001")])]))

ref = [A("get_quotes", component_id="C-N"), A("check_quote_validity", quote_id="QN1"),
       A("check_quote_validity", quote_id="QN2"), A("check_vendor_status", vendor_id="V2"),
       A("check_budget", budget_id="BUD-J"),
       A("create_purchase_order", project_id="PROJ-J", quote_id="QN2", quantity=30),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T10", "quote_conflict", "medium",
    "Buy 30 units of component C-N (Power Supply) for project PROJ-J from the cheapest quote that is "
    "still valid, and release the order. " + rules("PROJ-J", "jaya", "BUD-J", 10000),
    world([V("V1", "VoltLine"), V("V2", "AmpWorks")], [C("C-N", "Power Supply", 160, 30)],
          [Q("QN1", "V1", "C-N", 150, 50, expiry=0), Q("QN2", "V2", "C-N", 165, 50, ship=100)],
          [P("PROJ-J", "Project Juliet", "jaya", "BUD-J", 10000)], [B("BUD-J", 25000)]),
    {"orders": [order("PROJ-J", "C-N", vendor_id="V2", quantity=30, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("expired_quote", [ref[0], A("create_purchase_order", project_id="PROJ-J", quote_id="QN1",
                                       quantity=30), A("release_order", po_id="PO-0001")])]))

ref = [A("search_vendors"), A("get_quotes", component_id="C-O"), A("check_budget", budget_id="BUD-K"),
       A("check_vendor_status", vendor_id="V2"),
       A("create_purchase_order", project_id="PROJ-K", quote_id="QO2", quantity=20),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T11", "budget_constraint", "medium",
    "Buy 20 units of component C-O (Hydraulic Pump) for project PROJ-K and release the order. Prefer "
    "the company's preferred vendor if its quote fits in the remaining budget; otherwise use the "
    "cheapest valid quote that fits. " + rules("PROJ-K", "kai", "BUD-K", 15000),
    world([V("V1", "HydraCorp", preferred=True), V("V2", "PumpHouse")],
          [C("C-O", "Hydraulic Pump", 550, 20)],
          [Q("QO1", "V1", "C-O", 590, 20, ship=200), Q("QO2", "V2", "C-O", 440, 20, ship=100)],
          [P("PROJ-K", "Project Kilo", "kai", "BUD-K", 15000)], [B("BUD-K", 20000, extra_spent=10000)]),
    {"orders": [order("PROJ-K", "C-O", vendor_id="V2", quantity=20, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("preferred_over_budget", [ref[1], A("create_purchase_order", project_id="PROJ-K", quote_id="QO1",
                                               quantity=20), A("release_order", po_id="PO-0001")])]))

ref = [A("get_quotes", component_id="C-P"), A("check_budget", budget_id="BUD-L"),
       A("check_vendor_status", vendor_id="V1"), A("request_discount", quote_id="QP1", requested_price=490),
       A("create_purchase_order", project_id="PROJ-L", quote_id="QP1", quantity=20),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T12", "discount_negotiation", "medium",
    "Buy 20 units of component C-P (Drive Belt) for project PROJ-L and release the order. The only "
    "quote may exceed the budget: if so, negotiate a discount (vendors accept at most 10% off, once per "
    "quote) so the order fits. " + rules("PROJ-L", "lena", "BUD-L", 10000),
    world([V("V1", "BeltDrive Co")], [C("C-P", "Drive Belt", 520, 20)],
          [Q("QP1", "V1", "C-P", 520, 20, ship=100)],
          [P("PROJ-L", "Project Lima", "lena", "BUD-L", 10000)], [B("BUD-L", 10000)]),
    {"orders": [order("PROJ-L", "C-P", vendor_id="V1", quantity=20, status="RELEASED",
                      max_unit_price=495)], "max_new_orders": 1},
    ref, [("no_discount", [ref[0], ref[4], ref[5]])]))

ref = [A("check_existing_orders", project_id="PROJ-N"), A("check_budget", budget_id="BUD-N"),
       A("modify_order", po_id="PO-EX9", quantity=25),
       A("request_approval", po_id="PO-EX9", requester="nina"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-EX9")]
TASKS.append(task(
    "T14", "po_modification", "medium",
    "The requirement for component C-R on project PROJ-N changed from 10 to 25 units. Update the "
    "existing draft order (do not create a new one), get it approved, and release it. "
    + rules("PROJ-N", "nina", "BUD-N", 5000),
    world([V("V1", "GearSmith")], [C("C-R", "Gearbox", 700, 25)],
          [Q("QR1", "V1", "C-R", 700, 40)],
          [P("PROJ-N", "Project November", "nina", "BUD-N", 5000)], [B("BUD-N", 30000)],
          orders=[PO("PO-EX9", "V1", "C-R", 10, 700, "PROJ-N", "DRAFT")]),
    {"orders": [order("PROJ-N", "C-R", vendor_id="V1", quantity=25, status="RELEASED",
                      approval_valid=True)], "max_new_orders": 0},
    ref, [("not_modified", [ref[0], ref[3], ref[4], ref[5]])]))

# ═══ HARD ════════════════════════════════════════════════════════════════════

ref = [A("get_quotes", component_id="C-U"), A("check_vendor_status", vendor_id="V2"),
       A("check_vendor_status", vendor_id="V1"), A("get_quotes", component_id="C-V"),
       A("check_vendor_status", vendor_id="V3"), A("check_budget", budget_id="BUD-P"),
       A("create_purchase_order", project_id="PROJ-P", quote_id="QU1", quantity=20),
       A("create_purchase_order", project_id="PROJ-P", quote_id="QV1", quantity=30),
       A("request_approval", po_id="PO-0001", requester="pat"), A("approve_order", approval_id="APR-0001"),
       A("request_approval", po_id="PO-0002", requester="pat"), A("approve_order", approval_id="APR-0002"),
       A("release_order", po_id="PO-0001"), A("release_order", po_id="PO-0002")]
TASKS.append(task(
    "T16", "new_procurement", "hard",
    "Project PROJ-P needs 20 units of component C-U (Motor Driver) and 30 units of component C-V "
    "(Encoder). For each, use the cheapest valid quote (lowest total including shipping), then get "
    "the orders approved if needed and release both. " + rules("PROJ-P", "pat", "BUD-P", 10000),
    world([V("V1", "DriveTech"), V("V2", "BudgetDrives", approved=False, suspended=True),
           V("V3", "EncoderHub")],
          [C("C-U", "Motor Driver", 600, 20), C("C-V", "Encoder", 410, 30)],
          [Q("QU1", "V1", "C-U", 600, 30, ship=200), Q("QU2", "V2", "C-U", 550, 30),
           Q("QV1", "V3", "C-V", 400, 40), Q("QV2", "V1", "C-V", 420, 40, ship=100)],
          [P("PROJ-P", "Project Papa", "pat", "BUD-P", 10000)], [B("BUD-P", 80000)]),
    {"orders": [order("PROJ-P", "C-U", vendor_id="V1", quantity=20, status="RELEASED", approval_valid=True),
                order("PROJ-P", "C-V", vendor_id="V3", quantity=30, status="RELEASED", approval_valid=True)],
     "max_new_orders": 2},
    ref, [("suspended_vendor_for_C-U",
           [A("create_purchase_order", project_id="PROJ-P", quote_id="QU2", quantity=20)] + ref[7:])]))

ref = [A("check_existing_orders", project_id="PROJ-Q"), A("check_budget", budget_id="BUD-Q"),
       A("modify_order", po_id="PO-EX12", quantity=14),
       A("request_approval", po_id="PO-EX12", requester="quinn"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-EX12"),
       A("get_quotes", component_id="C-X"), A("check_quote_validity", quote_id="QX1"),
       A("check_vendor_status", vendor_id="V1"),
       A("create_purchase_order", project_id="PROJ-Q", quote_id="QX2", quantity=30),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T17", "complex_mixed", "hard",
    "For project PROJ-Q: (1) the requirement for component C-W changed from 10 to 14 units — update "
    "the existing order PO-EX12 (do not create a new C-W order), make sure it carries a valid approval, "
    "and release it; (2) buy 30 units of component C-X from the cheapest quote that is still valid and "
    "release that order too. " + rules("PROJ-Q", "quinn", "BUD-Q", 10000),
    world([V("V1", "QuantParts"), V("V2", "XpressSupply")],
          [C("C-W", "Actuator", 1100, 14), C("C-X", "Limit Switch", 260, 30)],
          [Q("QW1", "V1", "C-W", 1100, 20), Q("QX1", "V2", "C-X", 250, 50, expiry=0),
           Q("QX2", "V1", "C-X", 270, 50, ship=50)],
          [P("PROJ-Q", "Project Quebec", "quinn", "BUD-Q", 10000)], [B("BUD-Q", 60000)],
          orders=[PO("PO-EX12", "V1", "C-W", 10, 1100, "PROJ-Q", "APPROVED", approval_id="APR-EX12")],
          approvals=[APR("APR-EX12", "PO-EX12", "quinn")]),
    {"orders": [order("PROJ-Q", "C-W", vendor_id="V1", quantity=14, status="RELEASED", approval_valid=True),
                order("PROJ-Q", "C-X", vendor_id="V1", quantity=30, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("released_old_quantity", [ref[0], ref[5]] + ref[6:])]))

ref = [A("check_existing_orders", project_id="PROJ-R"), A("check_vendor_status", vendor_id="V3"),
       A("cancel_order", po_id="PO-EX13"), A("get_quotes", component_id="C-Y"),
       A("check_vendor_status", vendor_id="V2"), A("check_vendor_status", vendor_id="V1"),
       A("check_budget", budget_id="BUD-R"),
       A("create_purchase_order", project_id="PROJ-R", quote_id="QY1", quantity=25),
       A("request_approval", po_id="PO-0001", requester="rosa"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T18", "vendor_status", "hard",
    "Order PO-EX13 for 25 units of component C-Y on project PROJ-R was placed with a vendor whose "
    "standing may have changed. If that vendor is suspended or not approved, cancel PO-EX13 and replace "
    "it with a new order for 25 units from the cheapest valid quote. Get the replacement approved if "
    "needed and release it. " + rules("PROJ-R", "rosa", "BUD-R", 8000),
    world([V("V1", "RivetMasters"), V("V2", "NewRivets", approved=False),
           V("V3", "OldRivets", approved=False, suspended=True)],
          [C("C-Y", "Rivet Gun", 400, 25)],
          [Q("QY1", "V1", "C-Y", 410, 30, ship=100), Q("QY2", "V2", "C-Y", 360, 30),
           Q("QY3", "V3", "C-Y", 380, 30)],
          [P("PROJ-R", "Project Romeo", "rosa", "BUD-R", 8000)], [B("BUD-R", 40000)],
          orders=[PO("PO-EX13", "V3", "C-Y", 25, 380, "PROJ-R", "DRAFT")]),
    {"order_states": {"PO-EX13": "CANCELLED"},
     "orders": [order("PROJ-R", "C-Y", vendor_id="V1", quantity=25, status="RELEASED", approval_valid=True)],
     "max_new_orders": 1},
    ref, [("unapproved_replacement",
           ref[:4] + [A("create_purchase_order", project_id="PROJ-R", quote_id="QY2", quantity=25)] + ref[8:])]))

ref = [A("check_existing_orders", project_id="PROJ-S"), A("get_quotes", component_id="C-Z"),
       A("compare_quotes", quote_ids=["QZ1", "QZ2", "QZ3"]), A("check_vendor_status", vendor_id="V3"),
       A("check_vendor_status", vendor_id="V1"), A("check_budget", budget_id="BUD-S"),
       A("request_discount", quote_id="QZ1", requested_price=530),
       A("create_purchase_order", project_id="PROJ-S", quote_id="QZ1", quantity=40),
       A("request_approval", po_id="PO-0001", requester="sam"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T19", "discount_negotiation", "hard",
    "Project PROJ-S needs 40 units of component C-Z (Control Valve). Check existing orders first. Pick "
    "the cheapest valid quote (lowest total including shipping); if it exceeds the remaining budget, "
    "negotiate a discount on it (vendors accept at most 10% off, once per quote) so it fits. Then get "
    "approval if needed and release the order. " + rules("PROJ-S", "sam", "BUD-S", 10000),
    world([V("V1", "ValveKing"), V("V2", "FlowMasters"), V("V3", "DiscountValves", approved=False, suspended=True)],
          [C("C-Z", "Control Valve", 560, 40)],
          [Q("QZ1", "V1", "C-Z", 560, 50, ship=400), Q("QZ2", "V2", "C-Z", 575, 50),
           Q("QZ3", "V3", "C-Z", 500, 50)],
          [P("PROJ-S", "Project Sierra", "sam", "BUD-S", 10000)], [B("BUD-S", 30000, extra_spent=8000)],
          orders=[PO("PO-EX14", "V2", "C-Z", 40, 575, "PROJ-S", "CANCELLED")]),
    {"orders": [order("PROJ-S", "C-Z", vendor_id="V1", quantity=40, status="RELEASED", approval_valid=True,
                      max_unit_price=540)],
     "order_states": {"PO-EX14": "CANCELLED"}, "max_new_orders": 1},
    ref, [("no_discount_overrun", ref[:6] + ref[7:])]))

ref = [A("check_invoice", invoice_id="INV-4"), A("check_invoice", invoice_id="INV-5"),
       A("dispute_invoice", invoice_id="INV-5", reason="Amount does not match PO total"),
       A("check_existing_orders", project_id="PROJ-T"), A("check_budget", budget_id="BUD-T"),
       A("modify_order", po_id="PO-EX17", quantity=16),
       A("request_approval", po_id="PO-EX17", requester="tara"),
       A("approve_order", approval_id="APR-0001"), A("release_order", po_id="PO-EX17"),
       A("get_quotes", component_id="C-AD"), A("check_vendor_status", vendor_id="V2"),
       A("create_purchase_order", project_id="PROJ-T", quote_id="QAD1", quantity=10),
       A("release_order", po_id="PO-0001")]
TASKS.append(task(
    "T20", "complex_mixed", "hard",
    "For project PROJ-T: (1) check invoices INV-4 and INV-5 and dispute any whose amount does not "
    "match its PO total; (2) increase the existing draft order PO-EX17 for component C-AC from 12 to 16 "
    "units, get it approved if needed and release it; (3) buy 10 units of component C-AD from the "
    "cheapest valid quote and release that order. " + rules("PROJ-T", "tara", "BUD-T", 12000),
    world([V("V1", "TangoTech"), V("V2", "TerraParts")],
          [C("C-AA", "Mount Plate", 300, 20), C("C-AB", "Bearing", 1000, 8),
           C("C-AC", "Linear Rail", 900, 16), C("C-AD", "Belt Pulley", 450, 10)],
          [Q("QAC1", "V1", "C-AC", 900, 30), Q("QAD1", "V2", "C-AD", 450, 20),
           Q("QAD2", "V1", "C-AD", 440, 20, ship=200)],
          [P("PROJ-T", "Project Tango", "tara", "BUD-T", 12000)], [B("BUD-T", 70000)],
          orders=[PO("PO-EX15", "V1", "C-AA", 20, 300, "PROJ-T", "RELEASED"),
                  PO("PO-EX16", "V2", "C-AB", 8, 1000, "PROJ-T", "RELEASED"),
                  PO("PO-EX17", "V1", "C-AC", 12, 900, "PROJ-T", "DRAFT")],
          invoices=[INV("INV-4", "PO-EX15", 6000), INV("INV-5", "PO-EX16", 8500)]),
    {"invoice_states": {"INV-4": "unpaid", "INV-5": "disputed"},
     "orders": [order("PROJ-T", "C-AC", vendor_id="V1", quantity=16, status="RELEASED", approval_valid=True),
                order("PROJ-T", "C-AD", vendor_id="V2", quantity=10, status="RELEASED")],
     "max_new_orders": 1},
    ref, [("wrong_quote_and_no_dispute", ref[3:11] + [A("create_purchase_order", project_id="PROJ-T",
                                                        quote_id="QAD2", quantity=10),
                                                      A("release_order", po_id="PO-0001")])]))


def main():
    TASKS.sort(key=lambda t: t["id"])
    with open(OUT, "w") as f:
        for t in TASKS:
            f.write(json.dumps(t, sort_keys=False) + "\n")
    print(f"Wrote {len(TASKS)} tasks to {OUT}")


if __name__ == "__main__":
    main()
