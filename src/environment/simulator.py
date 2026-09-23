"""
simulator.py — Phase 1
The core procurement simulator.
- Holds the TRUE hidden state
- Exposes tool methods that return clean results
- Has a reset() method to restore to a known initial state per task
"""
import copy
from typing import Optional, Dict, Any
from .state import SimulatorState
from .entities import (
    Vendor, Component, SupplierQuote, Project,
    Budget, PurchaseOrder, Approval, Invoice, Shipment,
    POStatus, ApprovalStatus, QuoteStatus
)


class ProcurementSimulator:
    """
    The ground-truth simulator. Tool methods here return CLEAN results.
    The Fault Injector wraps these calls to corrupt results before the agent sees them.
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

    def advance_step(self):
        """Tick the simulator clock — used for quote expiry tracking."""
        self._true_state.step += 1

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
        step = self._true_state.step
        quotes = [
            {
                "id": q.id, "vendor_id": q.vendor_id,
                "unit_price": q.unit_price, "quantity": q.quantity,
                "shipping_cost": q.shipping_cost, "total_price": q.total_price,
                "status": q.status.value,
                "expired": step >= q.expiry_days
            }
            for q in self._true_state.quotes.values()
            if q.component_id == component_id
        ]
        return {"quotes": quotes}

    def check_quote_validity(self, quote_id: str) -> Dict[str, Any]:
        q = self._true_state.quotes.get(quote_id)
        if not q:
            return {"error": f"Quote {quote_id} not found"}
        expired = self._true_state.step >= q.expiry_days
        return {"id": q.id, "status": q.status.value, "expired": expired, "expiry_days": q.expiry_days}

    def check_budget(self, budget_id: str) -> Dict[str, Any]:
        b = self._true_state.budgets.get(budget_id)
        if not b:
            return {"error": f"Budget {budget_id} not found"}
        return {
            "id": b.id, "allocated": b.allocated, "spent": b.spent,
            "reserved": b.reserved, "remaining": b.remaining
        }

    def check_existing_orders(self, project_id: str) -> Dict[str, Any]:
        orders = [
            {"id": o.id, "vendor_id": o.vendor_id, "status": o.status.value, "total": o.total}
            for o in self._true_state.orders.values()
            if o.project_id == project_id
        ]
        return {"orders": orders}

    def compare_quotes(self, quote_ids: list) -> Dict[str, Any]:
        results = []
        for qid in quote_ids:
            q = self._true_state.quotes.get(qid)
            if q:
                results.append({
                    "id": q.id, "vendor_id": q.vendor_id,
                    "unit_price": q.unit_price, "total_price": q.total_price,
                    "shipping_cost": q.shipping_cost
                })
        results.sort(key=lambda x: x["total_price"])
        return {"ranked_quotes": results}

    def check_invoice(self, invoice_id: str) -> Dict[str, Any]:
        inv = self._true_state.invoices.get(invoice_id)
        if not inv:
            return {"error": f"Invoice {invoice_id} not found"}
        return {
            "id": inv.id, "po_id": inv.po_id, "amount": inv.amount,
            "line_items": inv.line_items, "mismatch": inv.mismatch, "status": inv.status
        }

    # ─── Tools — WRITE (Medium Risk) ──────────────────────────────────────────

    def request_discount(self, vendor_id: str, quote_id: str, requested_price: float) -> Dict[str, Any]:
        q = self._true_state.quotes.get(quote_id)
        if not q:
            return {"error": f"Quote {quote_id} not found"}
        # Simple rule: grant 5% discount if requested price is >= 95% of current
        if requested_price >= q.unit_price * 0.90:
            q.unit_price = requested_price
            return {"success": True, "new_unit_price": requested_price, "quote_id": quote_id}
        return {"success": False, "reason": "Requested discount too large", "min_price": q.unit_price * 0.90}

    def request_approval(self, po_id: str, requester: str) -> Dict[str, Any]:
        import uuid
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        approval_id = f"APR-{str(uuid.uuid4())[:8].upper()}"
        approval = Approval(
            id=approval_id, po_id=po_id,
            requester=requester, approver="manager",
            level="manager", status=ApprovalStatus.PENDING
        )
        self._true_state.approvals[approval_id] = approval
        po.status    = POStatus.PENDING
        po.approval_id = approval_id
        return {"approval_id": approval_id, "status": "PENDING", "po_id": po_id}

    # ─── Tools — WRITE (High Risk) ────────────────────────────────────────────

    def create_purchase_order(
        self, vendor_id: str, component_id: str,
        quantity: int, unit_price: float,
        project_id: str, shipping_cost: float = 0.0
    ) -> Dict[str, Any]:
        import uuid
        # Validate vendor
        vendor = self._true_state.vendors.get(vendor_id)
        if not vendor or not vendor.eligible or vendor.suspended:
            return {"error": "Vendor is not eligible or is suspended"}
        # Validate budget
        project = self._true_state.projects.get(project_id)
        if not project:
            return {"error": f"Project {project_id} not found"}
        budget = self._true_state.budgets.get(project.budget_id)
        total_cost = unit_price * quantity + shipping_cost
        if budget and budget.remaining < total_cost:
            return {"error": "Insufficient budget", "remaining": budget.remaining, "required": total_cost}
        # Create PO and reserve budget
        po_id = f"PO-{str(uuid.uuid4())[:8].upper()}"
        po = PurchaseOrder(
            id=po_id, vendor_id=vendor_id, component_id=component_id,
            quantity=quantity, unit_price=unit_price, shipping_cost=shipping_cost,
            project_id=project_id, status=POStatus.DRAFT
        )
        self._true_state.orders[po_id] = po
        if budget:
            budget.reserved += total_cost
        return {"po_id": po_id, "status": "DRAFT", "total": total_cost}

    def modify_order(self, po_id: str, quantity: int = None, unit_price: float = None) -> Dict[str, Any]:
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if po.status not in [POStatus.DRAFT, POStatus.PENDING]:
            return {"error": f"Cannot modify PO in status {po.status.value}"}
        # Invalidate existing approval if present
        if po.approval_id:
            apr = self._true_state.approvals.get(po.approval_id)
            if apr:
                apr.valid  = False
                apr.status = ApprovalStatus.INVALIDATED
        if quantity:
            po.quantity   = quantity
        if unit_price:
            po.unit_price = unit_price
        po.status = POStatus.DRAFT
        po.approval_id = None
        return {"po_id": po_id, "status": "DRAFT", "modified": True, "approval_invalidated": True}

    def approve_order(self, approval_id: str) -> Dict[str, Any]:
        apr = self._true_state.approvals.get(approval_id)
        if not apr:
            return {"error": f"Approval {approval_id} not found"}
        if not apr.valid:
            return {"error": "Approval is no longer valid (PO was modified)"}
        apr.status = ApprovalStatus.APPROVED
        po = self._true_state.orders.get(apr.po_id)
        if po:
            po.status = POStatus.APPROVED
        return {"approval_id": approval_id, "status": "APPROVED", "po_id": apr.po_id}

    def release_order(self, po_id: str) -> Dict[str, Any]:
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if po.status != POStatus.APPROVED:
            return {"error": f"PO must be APPROVED before release, current: {po.status.value}"}
        po.status   = POStatus.RELEASED
        po.released = True
        # Move budget from reserved → spent
        project = self._true_state.projects.get(po.project_id)
        if project:
            budget = self._true_state.budgets.get(project.budget_id)
            if budget:
                budget.reserved -= po.total
                budget.spent    += po.total
        return {"po_id": po_id, "status": "RELEASED"}

    def cancel_order(self, po_id: str) -> Dict[str, Any]:
        po = self._true_state.orders.get(po_id)
        if not po:
            return {"error": f"PO {po_id} not found"}
        if po.status == POStatus.RELEASED:
            return {"error": "Cannot cancel a released PO"}
        po.status = POStatus.CANCELLED
        # Free reserved budget
        project = self._true_state.projects.get(po.project_id)
        if project:
            budget = self._true_state.budgets.get(project.budget_id)
            if budget:
                budget.reserved = max(0, budget.reserved - po.total)
        return {"po_id": po_id, "status": "CANCELLED"}
