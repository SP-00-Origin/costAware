"""
validate.py — Phase 2
Validates the task dataset without any LLM:

  1. every reference trajectory runs on the CLEAN environment with no tool errors
     and the oracle returns PASS
  2. the empty trajectory (agent does nothing) FAILS
  3. every hand-written negative trajectory FAILS
  4. tier matches horizon: easy ≤ 5, medium 6–9, hard ≥ 10 reference actions
  5. the initial books are consistent (budget.reserved == sum of active PO totals)
"""
from typing import Any, Dict, List

from ..environment.env import ProcurementEnv
from ..environment.tasks import Task
from .oracle import oracle_check

TIER_BOUNDS = {"easy": (1, 5), "medium": (6, 9), "hard": (10, 99)}
ACTIVE = {"DRAFT", "PENDING_APPROVAL", "APPROVED"}


def run_trajectory(task: Task, actions: List[Dict[str, Any]], injector=None):
    env = ProcurementEnv(task, injector=injector)
    records = env.run_actions(actions)
    passed, diff = oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)
    return passed, diff, records


def validate_task(task: Task) -> List[str]:
    """Returns a list of problems (empty list = valid)."""
    problems = []

    lo, hi = TIER_BOUNDS.get(task.tier, (0, -1))
    n = len(task.reference_solution)
    if not lo <= n <= hi:
        problems.append(f"tier '{task.tier}' expects {lo}–{hi} actions, reference has {n}")

    state = task.build_state()
    for b in state.budgets.values():
        reserved = sum(o.total for o in state.orders.values()
                       if o.status.value in ACTIVE
                       and state.projects[o.project_id].budget_id == b.id)
        if abs(reserved - b.reserved) > 0.01:
            problems.append(f"budget {b.id} reserved={b.reserved} but active orders total {reserved}")

    passed, diff, records = run_trajectory(task, task.reference_solution)
    errors = [f"step {r['step']} {r['tool']}: {r['true_result']['error']}"
              for r in records if isinstance(r["true_result"], dict) and "error" in r["true_result"]]
    if errors:
        problems.append("reference has tool errors: " + "; ".join(errors))
    if not passed:
        failed = {k: v for k, v in diff.items() if not v["pass"]}
        problems.append(f"reference FAILS oracle: {failed}")

    if run_trajectory(task, [])[0]:
        problems.append("empty trajectory PASSES — task does not require any action")

    for neg in task.negatives:
        if run_trajectory(task, neg["trajectory"])[0]:
            problems.append(f"negative '{neg['name']}' PASSES but should FAIL")

    return problems


def validate_all(tasks: List[Task]) -> Dict[str, List[str]]:
    report = {}
    ids = [t.id for t in tasks]
    dup = {i for i in ids if ids.count(i) > 1}
    for t in tasks:
        problems = validate_task(t)
        if t.id in dup:
            problems.append("duplicate task id")
        report[t.id] = problems
    return report
