"""
state.py — Phase 1
SimulatorState: the hidden TRUE state of the procurement world.
Only the oracle and the simulator itself can read this directly.
The agent only ever sees tool output (which may be faulted).
"""
from pydantic import BaseModel, Field
from typing import Dict, Optional
from .entities import Vendor, Component, SupplierQuote, Project, Budget, PurchaseOrder, Approval, Invoice, Shipment


class SimulatorState(BaseModel):
    """
    Complete hidden ground truth of the procurement world.
    The agent NEVER reads this directly — it only sees tool outputs.
    The oracle uses this to evaluate final task success.
    """
    vendors:    Dict[str, Vendor]        = Field(default_factory=dict)
    components: Dict[str, Component]     = Field(default_factory=dict)
    quotes:     Dict[str, SupplierQuote] = Field(default_factory=dict)
    projects:   Dict[str, Project]       = Field(default_factory=dict)
    budgets:    Dict[str, Budget]        = Field(default_factory=dict)
    orders:     Dict[str, PurchaseOrder] = Field(default_factory=dict)
    approvals:  Dict[str, Approval]      = Field(default_factory=dict)
    invoices:   Dict[str, Invoice]       = Field(default_factory=dict)
    shipments:  Dict[str, Shipment]      = Field(default_factory=dict)
    step:       int = 0                  # current simulator step (for quote expiry)
