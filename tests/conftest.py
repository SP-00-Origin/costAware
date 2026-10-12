import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.environment.tasks import Task  # noqa: E402
from src.environment.simulator import ProcurementSimulator  # noqa: E402


def base_initial_state(threshold: float = 10000, allocated: float = 20000):
    """A small world: V1 good, V2 suspended, V3 not approved; one component, three quotes."""
    return {
        "vendors": [
            {"id": "V1", "name": "Good Ltd", "preferred": True},
            {"id": "V2", "name": "Suspended Inc", "approved": False, "suspended": True},
            {"id": "V3", "name": "Unapproved Co", "approved": False},
        ],
        "components": [{"id": "C-A", "name": "Board", "category": "electronics",
                        "reference_price": 500.0, "required_qty": 10, "available_qty": 50}],
        "quotes": [
            {"id": "Q1", "vendor_id": "V1", "component_id": "C-A", "unit_price": 480.0,
             "quantity": 20, "expiry_days": 100, "shipping_cost": 200.0},
            {"id": "Q2", "vendor_id": "V2", "component_id": "C-A", "unit_price": 400.0,
             "quantity": 20, "expiry_days": 100, "shipping_cost": 0.0},
            {"id": "Q3", "vendor_id": "V1", "component_id": "C-A", "unit_price": 450.0,
             "quantity": 20, "expiry_days": 3, "shipping_cost": 0.0},
        ],
        "projects": [{"id": "PROJ-A", "name": "Alpha", "owner": "alice", "budget_id": "BUD-A",
                      "procurement_rules": {"require_approval_above": threshold}}],
        "budgets": [{"id": "BUD-A", "allocated": allocated}],
    }


def make_task(initial_state=None, expected=None, **kw) -> Task:
    return Task(id=kw.get("id", "TEST"), family="test", tier="easy", goal="test",
                initial_state=initial_state or base_initial_state(),
                expected_final_state=expected or {}, reference_solution=kw.get("ref", []))


@pytest.fixture
def sim():
    s = ProcurementSimulator()
    s.load(make_task().build_state())
    return s
