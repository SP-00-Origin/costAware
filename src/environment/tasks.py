"""
tasks.py — Phase 1/2
Task schema, loader and the seeded initial-state generator.

A task (one line of tasks/tasks.jsonl) looks like:
{
  "id": "T01", "family": "new_procurement", "tier": "easy",
  "goal": "...natural-language instruction given to the agent...",
  "initial_state": {"vendors": [...], "components": [...], "quotes": [...],
                    "projects": [...], "budgets": [...], "orders": [...],
                    "approvals": [...], "invoices": [...], "shipments": [...]},
  "expected_final_state": {...oracle spec, see src/evaluation/oracle.py...},
  "reference_solution": [{"tool": "...", "args": {...}}, ...],
  "negatives": [{"name": "...", "trajectory": [...]}]     # optional, must FAIL
}
Entities are lists in JSON and become id-keyed dicts in SimulatorState.
"""
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .state import SimulatorState

DEFAULT_TASKS_PATH = Path(__file__).resolve().parents[2] / "tasks" / "tasks.jsonl"
ENTITY_KEYS = ["vendors", "components", "quotes", "projects", "budgets",
               "orders", "approvals", "invoices", "shipments"]
TIERS = ("easy", "medium", "hard")


class Task(BaseModel):
    id: str
    family: str
    tier: str
    goal: str
    initial_state: Dict[str, Any]
    expected_final_state: Dict[str, Any]
    reference_solution: List[Dict[str, Any]] = Field(default_factory=list)
    negatives: List[Dict[str, Any]] = Field(default_factory=list)

    def build_state(self) -> SimulatorState:
        return build_state(self.initial_state)


def build_state(initial_state: Dict[str, Any]) -> SimulatorState:
    """Turn a JSON initial_state (entity lists) into a validated SimulatorState."""
    data: Dict[str, Any] = {}
    for key in ENTITY_KEYS:
        items = initial_state.get(key, [])
        if isinstance(items, dict):           # already id-keyed
            items = list(items.values())
        keyed = {}
        for item in items:
            if item["id"] in keyed:
                raise ValueError(f"Duplicate {key} id {item['id']}")
            keyed[item["id"]] = item
        data[key] = keyed
    for key in ("step", "po_seq", "apr_seq"):
        if key in initial_state:
            data[key] = initial_state[key]
    return SimulatorState.model_validate(data)


def load_tasks(path: Optional[Path] = None) -> List[Task]:
    path = Path(path or DEFAULT_TASKS_PATH)
    tasks = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                tasks.append(Task.model_validate(json.loads(line)))
            except Exception as e:  # noqa: BLE001 — surface the line number
                raise ValueError(f"{path}:{lineno}: invalid task: {e}") from e
    return tasks


def get_task(task_id: str, path: Optional[Path] = None) -> Task:
    for t in load_tasks(path):
        if t.id == task_id:
            return t
    raise KeyError(f"Task {task_id} not found")


# ─── Seeded initial-state generator ──────────────────────────────────────────
# Template generator for the "new procurement" family, used to scale the
# dataset beyond the hand-written tasks (plan: 20 → 50 → 100 once stable).

def generate_procurement_task(seed: int, task_id: Optional[str] = None) -> Task:
    """
    Generate a solvable new-procurement task from a seed.
    Same seed → identical task. The cheapest quote may belong to a suspended
    vendor or be expired, so the correct choice depends on state, not on price alone.
    """
    rng = random.Random(seed)
    task_id = task_id or f"G{seed:04d}"
    comp_id, proj_id, bud_id, owner = "C-G1", "PROJ-G", "BUD-G", "dana"
    qty = rng.choice([5, 10, 15, 20, 25, 40])
    ref_price = rng.choice([80.0, 150.0, 240.0, 500.0, 900.0])
    n_vendors = rng.randint(2, 4)

    vendors, quotes = [], []
    for i in range(n_vendors):
        vid = f"V{i + 1}"
        vendors.append({"id": vid, "name": f"Vendor {i + 1}", "eligible": True,
                        "approved": True, "suspended": False, "preferred": i == 0})
        price = round(ref_price * rng.uniform(0.85, 1.15), 2)
        quotes.append({"id": f"Q{i + 1}", "vendor_id": vid, "component_id": comp_id,
                       "unit_price": price, "quantity": qty + rng.choice([0, 5, 10]),
                       "expiry_days": 100, "shipping_cost": float(rng.choice([0, 50, 100, 250]))})

    def total(q):
        return q["unit_price"] * qty + q["shipping_cost"]

    # Trap: make the cheapest quote unusable (suspended vendor or expired quote)
    cheapest = min(quotes, key=total)
    trap = rng.choice(["suspended", "expired", "none"])
    if trap == "suspended":
        v = next(v for v in vendors if v["id"] == cheapest["vendor_id"])
        v.update(suspended=True, approved=False)
    elif trap == "expired":
        cheapest["expiry_days"] = 0

    def usable(q):
        v = next(v for v in vendors if v["id"] == q["vendor_id"])
        return q["expiry_days"] > 0 and not v["suspended"] and v["approved"] and v["eligible"]

    candidates = [q for q in quotes if usable(q)]
    best = min(candidates, key=lambda q: (total(q), q["id"]))
    best_total = total(best)
    allocated = round(best_total * rng.uniform(1.3, 2.0), -2)
    threshold = rng.choice([0, best_total * 2])   # approval needed or not
    needs_approval = best_total > threshold

    goal = (f"Buy {qty} units of component {comp_id} for project {proj_id} (budget {bud_id}, "
            f"owner {owner}). Use the cheapest valid quote (lowest total including shipping) from a "
            f"vendor that is approved and not suspended, stay within budget, obtain approval if the "
            f"order needs it, and release the order.")
    ref = [{"tool": "get_quotes", "args": {"component_id": comp_id}}]
    for q in quotes:
        ref.append({"tool": "check_vendor_status", "args": {"vendor_id": q["vendor_id"]}})
    ref.append({"tool": "check_budget", "args": {"budget_id": bud_id}})
    ref.append({"tool": "create_purchase_order",
                "args": {"project_id": proj_id, "quote_id": best["id"], "quantity": qty}})
    if needs_approval:
        ref += [{"tool": "request_approval", "args": {"po_id": "PO-0001", "requester": owner}},
                {"tool": "approve_order", "args": {"approval_id": "APR-0001"}}]
    ref.append({"tool": "release_order", "args": {"po_id": "PO-0001"}})

    order_req = {"project_id": proj_id, "component_id": comp_id, "vendor_id": best["vendor_id"],
                 "quantity": qty, "status": "RELEASED"}
    if needs_approval:
        order_req["approval_valid"] = True

    return Task(
        id=task_id, family="new_procurement_generated",
        tier="hard" if len(ref) >= 10 else "medium" if len(ref) >= 6 else "easy",
        goal=goal,
        initial_state={
            "vendors": vendors,
            "components": [{"id": comp_id, "name": "Generated component", "category": "generated",
                            "reference_price": ref_price, "required_qty": qty, "available_qty": qty * 4}],
            "quotes": quotes,
            "projects": [{"id": proj_id, "name": "Generated project", "owner": owner, "budget_id": bud_id,
                          "procurement_rules": {"require_approval_above": threshold}}],
            "budgets": [{"id": bud_id, "allocated": allocated}],
        },
        expected_final_state={"orders": [order_req], "max_new_orders": 1},
        reference_solution=ref,
    )
