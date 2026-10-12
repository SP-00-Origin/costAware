"""
simulator.py — Phase 1
The core procurement simulator.
- Holds the TRUE hidden state
- Exposes tool methods that return clean results
- Has a reset() method to restore to a known initial state per task

Design rule (important for the research question)
--------------------------------------------------
The simulator enforces the *workflow state machine* and referential integrity
(unknown IDs, illegal status transitions, missing approval above the project
threshold). It does NOT stop the agent from making *policy* mistakes — ordering
from a suspended / unapproved vendor, overrunning the budget, ordering on an
expired quote, or creating duplicate orders. Those actions go through, exactly
like in a real ERP, and the deterministic oracle catches them at the end.
If the simulator blocked every bad action, injected faults could never cause
a task failure and Policies A–D would be indistinguishable.

All IDs the simulator creates are sequential (PO-0001, APR-0001) so that the
same task + seed always produces the same trajectory.
"""
from typing import Optional, Dict, Any, List
from .state import SimulatorState
from .entities import (
    Approval, PurchaseOrder, POStatus, ApprovalStatus, QuoteStatus,
)

ACTIVE_PO_STATUSES = {POStatus.DRAFT, POStatus.PENDING, POStatus.APPROVED}


class ProcurementSimulator:
    """
    The ground-truth simulator. Tool methods here return CLEAN results.
    The Fault Injector wraps these calls to corrupt results before the agent sees them.
    Tool methods never raise for bad input: they return {"error": ...} so that
    the agent sees the failure as an observation.
    """

    def __init__(self):
        self._true_state: Optional[SimulatorState] = None
        self._initial_state: Optional[SimulatorState] = None   # snapshot for reset

    # ─── Setup ────────────────────────────────────────────────────────────────

    def load(self, state: SimulatorState):
        """Load a SimulatorState (from a task definition)."""
        self._initial_state = state.model_copy(deep=True)
        self._true_state    = state.model_copy(deep=True)

    def reset(self):
        """Reset to initial state — called between trials."""
        assert self._initial_state is not None, "Call load() first."
        self._true_state = self._initial_state.model_copy(deep=True)

    @property
    def state(self) -> SimulatorState:
        """Access the hidden true state (oracle only)."""
        return self._true_state

    @property
    def initial_state(self) -> SimulatorState:
        return self._initial_state

    def advance_step(self):
        """Tick the simulator clock — used for quote expiry tracking."""
        self._true_state.step += 1

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _budget_for_project(self, project_id: str):
        project = self._true_state.projects.get(project_id)
        if not project:
            return None
        return self._true_state.budgets.get(project.budget_id)

    def _approval_threshold(self, project_id: str) -> float:
        project = self._true_state.projects.get(project_id)
        if not project:
            return 0.0
        return float(project.procurement_rules.get("require_approval_above", 0))

    def requires_approval(self, po: PurchaseOrder) -> bool:
        return po.total > self._approval_threshold(po.project_id)

    def _quote_status(self, q) -> str:
        if q.status == QuoteStatus.USED:
            return QuoteStatus.USED.value
        return QuoteStatus.EXPIRED.value if q.is_expired(self._true_state.step) else QuoteStatus.ACTIVE.value

    def _invalidate_approval(self, po: PurchaseOrder):
        if po.approval_id:
            apr = self._true_state.approvals.get(po.approval_id)
            if apr:
                apr.valid  = False
                apr.status = ApprovalStatus.INVALIDATED
        po.approval_id = None

    # ─── Tools — READ (Low Risk) ───────────────────────────────────────────────

    def search_vendors(self) -> Dict[str, Any]:
        return {
            "vendors": [
                {"id": v.id, "name": v.name, "preferred": v.preferred}
                for v in self._true_state.vendors.values()
            ]
        }

    def get_vendor_details(self, vendor_id: str) -> Dict[str, Any]:
        v = self._true_state.vendors.get(vendor_id)
        if not v:
            return {"error": f"Vendor {vendor_id} not found"}
        return {
            "id": v.id, "name": v.name, "eligible": v.eligible,
            "approved": v.approved, "preferred": v.preferred,
            "payment_profile": v.payment_profile
        }

    def check_vendor_status(self, vendor_id: str) -> Dict[str, Any]:
        v = self._true_state.vendors.get(vendor_id)
        if not v:
            return {"error": f"Vendor {vendor_id} not found"}
        return {"id": v.id, "approved": v.approved, "suspended": v.suspended, "eligible": v.eligible}

    def get_quotes(self, component_id: str) -> Dict[str, Any]:
        if component_id not in self._true_state.components:
            return {"error": f"Component {component_id} not found"}
        quotes = [
            {
                "id": q.id, "vendor_id": q.vendor_id,
                "unit_price": q.unit_price, "quantity": q.quantity,
                "shipping_cost": q.shipping_cost, "total_price": q.total_price,
                "status": self._quote_status(q),
                "expired": q.is_expired(self._true_state.step),
            }
            for q in self._true_state.quotes.values()
            if q.component_id == component_id
        ]
        return {"component_id": component_id, "quotes": quotes}

    def check_quote_validity(self, quote_id: str) -> Dict[str, Any]:
        q = self._true_state.quotes.get(quote_id)
        if not q:
            return {"error": f"Quote {quote_id} not found"}
        return {
            "id": q.id, "status": self._quote_status(q),
            "expired": q.is_expired(self._true_state.step),
            "expiry_days": q.expiry_days, "current_step": self._true_state.step,
        }

    def check_budget(self, budget_id: str) -> Dict[str, Any]:
        b = self._true_state.budgets.get(budget_id)
        if not b:
            return {"error": f"Budget {budget_id} not found"}
        return {
            "id": b.id, "allocated": b.allocated, "spent": b.spent,
            "reserved": b.reserved, "remaining": b.remaining
        }

    def check_existing_orders(self, project_id: str) -> Dict[str, Any]:
        if project_id not in self._true_state.projects:
            return {"error": f"Project {project_id} not found"}
        orders = [
            {
                "id": o.id, "vendor_id": o.vendor_id, "component_id": o.component_id,
                "quantity": o.quantity, "unit_price": o.unit_price,
                "status": o.status.value, "total": o.total,
                "approval_id": o.approval_id,
            }
            for o in self._true_state.orders.values()
            if o.project_id == project_id
        ]
        return {"project_id": project_id, "orders": orders}

    def compare_quotes(self, quote_ids: List[str]) -> Dict[str, Any]:
        results, missing = [], []
        for qid in quote_ids:
            q = self._true_state.quotes.get(qid)
            if q:
                results.append({
                    "id": q.id, "vendor_id": q.vendor_id,
                    "unit_price": q.unit_price, "total_price": q.total_price,
                    "shipping_cost": q.shipping_cost,
                    "expired": q.is_expired(self._true_state.step),
                })
            else:
                missing.append(qid)
        results.sort(key=lambda x: (x["total_price"], x["id"]))
        out = {"ranked_quotes": results}
        if missing:
            out["not_found"] = missing
        return out

    def check_invoice(self, invoice_id: str) -> Dict[str, Any]:
        inv = self._true_state.invoices.get(invoice_id)
        if not inv:
            return {"error": f"Invoice {invoice_id} not found"}
        po = self._true_state.orders.get(inv.po_id)
        po_total = po.total if po else None
        mismatch = inv.mismatch or (po_total is not None and abs(inv.amount - po_total) > 0.01)
        return {
            "id": inv.id, "po_id": inv.po_id, "amount": inv.amount,
            "po_total": po_total, "line_items": inv.line_items,
            "mismatch": mismatch, "status": inv.status
        }

    # ─── Tools — WRITE (Medium Risk) ──────────────────────────────────────────

    def request_discount(self, quote_id: str, requested_price: float) -> Dict[str, Any]:
        """Vendor accepts a new unit price if it is >= 90% of the current price.
        A quote can only be renegotiated once."""
        q = self._true_state.quotes.get(quote_id)
        if not q:
            return {"error": f"Quote {quote_id} not found"}
        if q.discount_used:
            return {"success": False, "reason": "Discount already negotiated for this quote",
                    "unit_price": q.unit_price}
        floor = round(q.unit_price * 0.90, 2)
        if requested_price >= floor:
            q.unit_price    = float(requested_price)
            q.discount_used = True
            return {"success": True, "quote_id": quote_id, "new_unit_price": q.unit_price,
                    "new_total_price": q.total_price}
        return {"success": False, "reason": "Requested discount too large", "min_unit_price": floor}

    def request_approval(self, po_id: str, requester: str) -> Dict[str, Any]:
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if po.status != POStatus.DRAFT:
            return {"error": f"Approval can only be requested for a DRAFT PO, current: {po.status.value}"}
        project = self._true_state.projects.get(po.project_id)
        if project and requester != project.owner:
            return {"error": f"Requester '{requester}' is not the owner of project {po.project_id}"}
        self._true_state.apr_seq += 1
        approval_id = f"APR-{self._true_state.apr_seq:04d}"
        self._true_state.approvals[approval_id] = Approval(
            id=approval_id, po_id=po_id,
            requester=requester, approver="manager",
            level="manager", status=ApprovalStatus.PENDING,
        )
        po.status      = POStatus.PENDING
        po.approval_id = approval_id
        return {"approval_id": approval_id, "status": ApprovalStatus.PENDING.value, "po_id": po_id}

    def dispute_invoice(self, invoice_id: str, reason: str = "") -> Dict[str, Any]:
        inv = self._true_state.invoices.get(invoice_id)
        if not inv:
            return {"error": f"Invoice {invoice_id} not found"}
        if inv.status == "paid":
            return {"error": "Cannot dispute a paid invoice"}
        inv.status = "disputed"
        return {"id": invoice_id, "status": "disputed", "reason": reason}

    # ─── Tools — WRITE (High Risk) ────────────────────────────────────────────

    def create_purchase_order(self, project_id: str, quote_id: str, quantity: int) -> Dict[str, Any]:
        """Create a DRAFT PO priced from a supplier quote and reserve budget.
        Vendor standing, budget headroom and quote expiry are NOT enforced here —
        that is the agent's responsibility and the oracle's job to check."""
        project = self._true_state.projects.get(project_id)
        if not project:
            return {"error": f"Project {project_id} not found"}
        q = self._true_state.quotes.get(quote_id)
        if not q:
            return {"error": f"Quote {quote_id} not found"}
        if not isinstance(quantity, int) or quantity <= 0:
            return {"error": "Quantity must be a positive integer"}
        if quantity > q.quantity:
            return {"error": f"Quote {quote_id} only covers {q.quantity} units"}
        if q.vendor_id not in self._true_state.vendors:
            return {"error": f"Vendor {q.vendor_id} not found"}

        self._true_state.po_seq += 1
        po_id = f"PO-{self._true_state.po_seq:04d}"
        po = PurchaseOrder(
            id=po_id, vendor_id=q.vendor_id, component_id=q.component_id,
            quantity=quantity, unit_price=q.unit_price, shipping_cost=q.shipping_cost,
            project_id=project_id, status=POStatus.DRAFT,
            quote_id=quote_id, created_step=self._true_state.step,
        )
        self._true_state.orders[po_id] = po
        budget = self._budget_for_project(project_id)
        if budget:
            budget.reserved += po.total
        return {
            "po_id": po_id, "status": po.status.value, "vendor_id": po.vendor_id,
            "component_id": po.component_id, "quantity": quantity,
            "unit_price": po.unit_price, "total": po.total,
            "requires_approval": self.requires_approval(po),
        }

    def modify_order(self, po_id: str, quantity: int) -> Dict[str, Any]:
        """Change PO quantity. Any existing approval is invalidated and the PO
        returns to DRAFT; budget reservation is adjusted by the difference."""
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if po.status not in ACTIVE_PO_STATUSES:
            return {"error": f"Cannot modify PO in status {po.status.value}"}
        if not isinstance(quantity, int) or quantity <= 0:
            return {"error": "Quantity must be a positive integer"}
        had_approval = po.approval_id is not None
        old_total    = po.total
        po.quantity  = quantity
        budget = self._budget_for_project(po.project_id)
        if budget:
            budget.reserved += po.total - old_total
        self._invalidate_approval(po)
        po.status = POStatus.DRAFT
        return {
            "po_id": po_id, "status": po.status.value, "quantity": quantity,
            "total": po.total, "approval_invalidated": had_approval,
            "requires_approval": self.requires_approval(po),
        }

    def approve_order(self, approval_id: str) -> Dict[str, Any]:
        apr = self._true_state.approvals.get(approval_id)
        if not apr:
            return {"error": f"Approval {approval_id} not found"}
        if not apr.valid:
            return {"error": "Approval is no longer valid (PO was modified)"}
        if apr.status != ApprovalStatus.PENDING:
            return {"error": f"Approval is not pending, current: {apr.status.value}"}
        po = self._true_state.orders.get(apr.po_id)
        if not po or po.status != POStatus.PENDING:
            return {"error": "PO is not awaiting approval"}
        apr.status = ApprovalStatus.APPROVED
        po.status  = POStatus.APPROVED
        return {"approval_id": approval_id, "status": ApprovalStatus.APPROVED.value, "po_id": apr.po_id}

    def release_order(self, po_id: str) -> Dict[str, Any]:
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if self.requires_approval(po):
            apr = self._true_state.approvals.get(po.approval_id) if po.approval_id else None
            if po.status != POStatus.APPROVED or not apr or not apr.valid:
                return {"error": f"PO total {po.total} needs a valid approval before release, "
                                 f"current status: {po.status.value}"}
        elif po.status not in (POStatus.DRAFT, POStatus.APPROVED):
            return {"error": f"PO cannot be released from status {po.status.value}"}
        po.status   = POStatus.RELEASED
        po.released = True
        budget = self._budget_for_project(po.project_id)
        if budget:
            budget.reserved = max(0.0, budget.reserved - po.total)
            budget.spent   += po.total
        return {"po_id": po_id, "status": po.status.value}

    def cancel_order(self, po_id: str) -> Dict[str, Any]:
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if po.status == POStatus.RELEASED:
            return {"error": "Cannot cancel a released PO"}
        if po.status == POStatus.CANCELLED:
            return {"error": "PO is already cancelled"}
        po.status = POStatus.CANCELLED
        self._invalidate_approval(po)
        budget = self._budget_for_project(po.project_id)
        if budget:
            budget.reserved = max(0.0, budget.reserved - po.total)
        return {"po_id": po_id, "status": po.status.value}
