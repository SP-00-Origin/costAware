"""
entities.py — Phase 1
All 9 simulator entities as Pydantic models.
These are the core data structures of the procurement world.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class POStatus(str, Enum):
    NOT_CREATED  = "NOT_CREATED"
    DRAFT        = "DRAFT"
    PENDING      = "PENDING_APPROVAL"
    APPROVED     = "APPROVED"
    RELEASED     = "RELEASED"
    CANCELLED    = "CANCELLED"

class ApprovalStatus(str, Enum):
    PENDING    = "PENDING"
    APPROVED   = "APPROVED"
    REJECTED   = "REJECTED"
    INVALIDATED = "INVALIDATED"   # happens after PO modification

class QuoteStatus(str, Enum):
    ACTIVE  = "ACTIVE"
    EXPIRED = "EXPIRED"
    USED    = "USED"

class ShipmentStatus(str, Enum):
    NOT_DISPATCHED = "NOT_DISPATCHED"
    DISPATCHED     = "DISPATCHED"
    DELIVERED      = "DELIVERED"


# ─── Entity Models ─────────────────────────────────────────────────────────────

class Vendor(BaseModel):
    id:               str
    name:             str
    eligible:         bool = True
    approved:         bool = True
    suspended:        bool = False
    preferred:        bool = False
    payment_profile:  str  = "standard"   # e.g. "net30", "prepaid"


class Component(BaseModel):
    id:              str
    name:            str
    category:        str
    reference_price: float
    required_qty:    int
    available_qty:   int


class SupplierQuote(BaseModel):
    id:           str
    vendor_id:    str
    component_id: str
    unit_price:   float
    quantity:     int
    expiry_days:  int        # how many steps until expiry
    shipping_cost: float = 0.0
    status:       QuoteStatus = QuoteStatus.ACTIVE

    @property
    def total_price(self) -> float:
        return self.unit_price * self.quantity + self.shipping_cost


class Project(BaseModel):
    id:                str
    name:              str
    owner:             str
    budget_id:         str
    procurement_rules: dict = Field(default_factory=dict)  # e.g. {"require_approval_above": 10000}
    priority:          str  = "normal"


class Budget(BaseModel):
    id:        str
    allocated: float
    spent:     float = 0.0
    reserved:  float = 0.0

    @property
    def remaining(self) -> float:
        return self.allocated - self.spent - self.reserved


class PurchaseOrder(BaseModel):
    id:           str
    vendor_id:    str
    component_id: str
    quantity:     int
    unit_price:   float
    shipping_cost: float = 0.0
    project_id:   str
    status:       POStatus = POStatus.DRAFT
    approval_id:  Optional[str] = None
    released:     bool = False

    @property
    def total(self) -> float:
        return self.unit_price * self.quantity + self.shipping_cost


class Approval(BaseModel):
    id:        str
    po_id:     str
    requester: str
    approver:  str
    level:     str   # "manager", "director", etc.
    status:    ApprovalStatus = ApprovalStatus.PENDING
    valid:     bool = True   # becomes False if PO is modified after approval


class Invoice(BaseModel):
    id:           str
    po_id:        str
    amount:       float
    line_items:   List[dict] = Field(default_factory=list)
    mismatch:     bool = False
    status:       str = "unpaid"   # "unpaid", "paid", "disputed"


class Shipment(BaseModel):
    id:          str
    po_id:       str
    quantity:    int
    destination: str
    status:      ShipmentStatus = ShipmentStatus.NOT_DISPATCHED
