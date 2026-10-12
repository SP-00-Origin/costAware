"""Phase 2 — task dataset and deterministic oracle."""
import ast
import json
from pathlib import Path

import pytest

from src.environment.env import ProcurementEnv
from src.environment.tasks import load_tasks, generate_procurement_task, DEFAULT_TASKS_PATH
from src.evaluation.oracle import oracle_check
from src.evaluation.validate import validate_task, run_trajectory
from tests.conftest import make_task, base_initial_state

TASKS = load_tasks()
ROOT = Path(__file__).resolve().parents[1]


def test_dataset_size_and_coverage():
    assert len(TASKS) == 20
    assert len({t.id for t in TASKS}) == 20
    assert {t.tier for t in TASKS} == {"easy", "medium", "hard"}
    assert len({t.family for t in TASKS}) >= 10
    assert all(t.negatives for t in TASKS)


def test_tasks_jsonl_is_valid_jsonl():
    with open(DEFAULT_TASKS_PATH) as f:
        for line in f:
            json.loads(line)


def test_tasks_jsonl_in_sync_with_builder(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_tasks", ROOT / "tasks" / "build_tasks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "tasks.jsonl"
    monkeypatch.setattr(mod, "OUT", out)
    mod.main()
    assert out.read_text() == DEFAULT_TASKS_PATH.read_text(), "run: python tasks/build_tasks.py"


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_task_is_valid(task):
    """Reference PASSes with no tool errors; empty and negative trajectories FAIL."""
    assert validate_task(task) == []


@pytest.mark.parametrize("seed", range(50))
def test_generated_tasks_are_valid(seed):
    assert validate_task(generate_procurement_task(seed)) == []


def test_oracle_never_imports_an_llm():
    src = (ROOT / "src" / "evaluation" / "oracle.py").read_text()
    imported = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom))}
    assert not imported & {"anthropic", "langchain", "langchain_anthropic", "langgraph", "openai"}


def test_oracle_reads_true_state_not_observations():
    """Same actions, different faults → same oracle verdict (oracle only sees true state)."""
    task = TASKS[0]

    class LyingInjector:
        def reset(self): pass
        def inject(self, tool, args, true_result):
            return {"error": "lies"}, "corrupted_obs"

    clean = run_trajectory(task, task.reference_solution)[0]
    faulty = run_trajectory(task, task.reference_solution, injector=LyingInjector())[0]
    assert clean is True and faulty is True


def test_empty_spec_never_passes():
    env = ProcurementEnv(make_task())
    passed, diff = oracle_check(env.true_state, {}, env.sim.initial_state)
    assert passed is False and all(v["pass"] for v in diff.values())


def test_duplicate_orders_detected():
    env = ProcurementEnv(make_task())
    env.call("create_purchase_order", {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 5})
    env.call("create_purchase_order", {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 5})
    passed, diff = oracle_check(env.true_state, {"orders": [{"project_id": "PROJ-A", "component_id": "C-A"}]},
                                env.sim.initial_state)
    assert not passed
    assert diff["no_duplicate_orders"]["pass"] is False


def test_cancelled_duplicate_is_fine():
    env = ProcurementEnv(make_task())
    env.call("create_purchase_order", {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 5})
    env.call("cancel_order", {"po_id": "PO-0001"})
    env.call("create_purchase_order", {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 10})
    env.call("release_order", {"po_id": "PO-0002"})
    passed, _ = oracle_check(env.true_state, {"orders": [{"project_id": "PROJ-A", "component_id": "C-A",
                                                          "quantity": 10, "status": "RELEASED"}]},
                             env.sim.initial_state)
    assert passed


def test_legacy_expected_keys_still_work():
    st = base_initial_state()
    st["vendors"].append({"id": "VX", "name": "x"})
    env = ProcurementEnv(make_task(st))
    env.call("create_purchase_order", {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 10})
    env.call("release_order", {"po_id": "PO-0001"})
    passed, diff = oracle_check(env.true_state, {"po_id": "PO-0001", "po_status": "RELEASED", "vendor_id": "V1",
                                                 "budget_id": "BUD-A", "no_suspended_vendor": True,
                                                 "expected_quantity": 10}, env.sim.initial_state)
    assert passed, diff
