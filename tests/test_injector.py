"""Phase 3 — fault injector and replay."""
import copy

import pytest

from src.environment.env import ProcurementEnv
from src.environment.tasks import load_tasks
from src.faults.injector import FaultInjector, FAULT_TYPES
from src.faults.replay import ReplayInjector, replay_records, save_records, load_records

TASKS = {t.id: t for t in load_tasks()}

BUDGET = {"id": "BUD-A", "allocated": 20000.0, "spent": 0.0, "reserved": 5000.0, "remaining": 15000.0}
QUOTES = {"component_id": "C-A", "quotes": [
    {"id": "Q1", "vendor_id": "V1", "unit_price": 480.0, "status": "EXPIRED", "expired": True},
    {"id": "Q2", "vendor_id": "V2", "unit_price": 500.0, "status": "ACTIVE", "expired": False}]}
VENDOR = {"id": "V2", "approved": False, "suspended": True, "eligible": True}
PO = {"po_id": "PO-0001", "status": "DRAFT", "total": 5000.0, "requires_approval": False}


def only(fault, **kw):
    return FaultInjector(seed=1, fault_rate=1.0, fault_types=[fault], **kw)


# ─── Each fault type, on a result where it applies ───────────────────────────

def test_wrong_value_changes_a_number_by_10_to_30_percent():
    obs, f = only("wrong_value").inject("check_budget", {"budget_id": "BUD-A"}, BUDGET)
    assert f == "wrong_value"
    diff = [(k, BUDGET[k], obs[k]) for k in BUDGET if obs[k] != BUDGET[k]]
    assert len(diff) == 1
    _, true, seen = diff[0]
    assert 0.09 <= abs(seen - true) / true <= 0.31


def test_corrupted_obs_zeroes_a_number():
    obs, f = only("corrupted_obs").inject("check_budget", {"budget_id": "BUD-A"}, BUDGET)
    assert f == "corrupted_obs"
    assert [k for k in BUDGET if obs[k] != BUDGET[k] and obs[k] == 0]


def test_contradictory_flips_a_boolean():
    obs, f = only("contradictory").inject("check_vendor_status", {"vendor_id": "V2"}, VENDOR)
    assert f == "contradictory"
    assert sum(obs[k] != VENDOR[k] for k in VENDOR) == 1


def test_malformed_output_loses_structure():
    obs, f = only("malformed_output").inject("get_quotes", {"component_id": "C-A"}, QUOTES)
    assert f == "malformed_output" and obs["parse_error"] is True and isinstance(obs["raw"], str)
    assert "quotes" not in obs


def test_missing_field_drops_a_key():
    obs, f = only("missing_field").inject("check_budget", {"budget_id": "BUD-A"}, BUDGET)
    assert f == "missing_field" and len(obs) == len(BUDGET) - 1


def test_missing_field_reaches_nested_records():
    inj = FaultInjector(seed=3, fault_rate=1.0, fault_types=["missing_field"])
    dropped_nested = False
    for i in range(30):
        obs, _ = inj.inject("get_quotes", {"component_id": f"C-{i}"}, QUOTES)
        if "quotes" in obs and any(len(q) < 5 for q in obs["quotes"]):
            dropped_nested = True
    assert dropped_nested


def test_timeout_fires_and_returns_error():
    obs, f = only("timeout").inject("create_purchase_order", {"quote_id": "Q1"}, PO)
    assert f == "timeout" and obs["timeout"] is True and "error" in obs


def test_incorrect_status_uses_plausible_wrong_status():
    obs, f = only("incorrect_status").inject("create_purchase_order", {"quote_id": "Q1"}, PO)
    assert f == "incorrect_status" and obs["status"] == "APPROVED"


def test_stale_info_returns_previous_view_of_same_call():
    inj = FaultInjector(seed=1, fault_rate=0.0)
    inj.inject("check_budget", {"budget_id": "BUD-A"}, BUDGET)          # first, clean view
    newer = dict(BUDGET, reserved=9000.0, remaining=11000.0)
    inj.fault_rate, inj.fault_types = 1.0, ["stale_info"]
    obs, f = inj.inject("check_budget", {"budget_id": "BUD-A"}, newer)
    assert f == "stale_info" and obs == BUDGET                          # the OLD snapshot


def test_stale_info_synthesises_older_view_on_first_call():
    obs, f = only("stale_info").inject("get_quotes", {"component_id": "C-A"}, QUOTES)
    assert f == "stale_info"
    assert obs["quotes"][0]["status"] == "ACTIVE" and obs["quotes"][0]["expired"] is False


def test_inapplicable_fault_is_not_reported():
    """A result with no numbers cannot get corrupted_obs → reported as clean, not as a fault."""
    res = {"vendors": [{"id": "V1", "name": "x"}]}
    obs, f = only("corrupted_obs").inject("search_vendors", {}, res)
    assert f is None and obs == res


@pytest.mark.parametrize("fault", FAULT_TYPES)
def test_every_fault_type_occurs_in_real_episodes(fault):
    """Across the dataset, every fault type actually fires and visibly changes the observation."""
    seen = 0
    for seed in range(5):
        for task in TASKS.values():
            env = ProcurementEnv(task, FaultInjector(seed=seed, fault_rate=1.0, fault_types=[fault]))
            for r in env.run_actions(task.reference_solution):
                if r["fault_injected"] == fault:
                    assert r["observed_result"] != r["true_result"]
                    seen += 1
    assert seen > 0


# ─── Ground truth is never touched ───────────────────────────────────────────

def test_injector_never_mutates_true_result():
    snapshot = copy.deepcopy(QUOTES)
    inj = FaultInjector(seed=0, fault_rate=1.0)
    for i in range(50):
        inj.inject("get_quotes", {"component_id": f"C-{i}"}, QUOTES)
    assert QUOTES == snapshot


def test_faults_do_not_change_true_state_trajectory():
    task = TASKS["T16"]
    clean = ProcurementEnv(task)
    clean.run_actions(task.reference_solution)
    faulty = ProcurementEnv(task, FaultInjector(seed=9, fault_rate=1.0))
    faulty.run_actions(task.reference_solution)
    assert clean.true_state.model_dump() == faulty.true_state.model_dump()
    assert any(r["fault_injected"] for r in faulty.records)


# ─── Reproducibility ─────────────────────────────────────────────────────────

def _faults(task, seed, rate=0.4):
    env = ProcurementEnv(task, FaultInjector(seed=seed, fault_rate=rate))
    return [(r["fault_injected"], r["observed_result"]) for r in env.run_actions(task.reference_solution)]


def test_same_seed_same_faults():
    for task in TASKS.values():
        assert _faults(task, 42) == _faults(task, 42)


def test_different_seed_different_faults():
    t = TASKS["T20"]
    assert any(_faults(t, s) != _faults(t, 0) for s in range(1, 5))


def test_fault_on_an_action_does_not_depend_on_extra_calls():
    """Policy B's extra verification calls must not shift the fault schedule of later actions."""
    task = TASKS["T07"]
    plain = ProcurementEnv(task, FaultInjector(seed=5, fault_rate=0.5))
    a = [r["fault_injected"] for r in plain.run_actions(task.reference_solution)]

    verified = ProcurementEnv(task, FaultInjector(seed=5, fault_rate=0.5))
    b = []
    for act in task.reference_solution:
        b.append(verified.call(act["tool"], act["args"])["fault_injected"])
        # extra verification call that is not itself one of the reference actions
        verified.call("get_vendor_details", {"vendor_id": "V1"}, origin="recovery")
    assert a == b


def test_recall_of_same_tool_is_independent_roll():
    inj = FaultInjector(seed=0, fault_rate=0.5)
    outcomes = {inj.inject("check_budget", {"budget_id": "B"}, BUDGET)[1] for _ in range(40)}
    assert None in outcomes and len(outcomes) > 1


def test_empirical_fault_rate_matches_setting():
    for rate in (0.1, 0.25, 0.4):
        inj = FaultInjector(seed=11, fault_rate=rate)
        n = 4000
        hits = sum(inj.inject("check_budget", {"budget_id": f"B{i}"}, BUDGET)[1] is not None for i in range(n))
        assert abs(hits / n - rate) < 0.03, (rate, hits / n)


def test_zero_rate_and_never_fault():
    inj = FaultInjector(seed=1, fault_rate=0.0)
    assert all(inj.inject("check_budget", {"budget_id": str(i)}, BUDGET)[1] is None for i in range(200))
    inj = FaultInjector(seed=1, fault_rate=1.0, never_fault=["check_budget"])
    assert inj.inject("check_budget", {"budget_id": "B"}, BUDGET) == (BUDGET, None)


def test_bad_config_rejected():
    with pytest.raises(ValueError):
        FaultInjector(fault_types=["nope"])
    with pytest.raises(ValueError):
        FaultInjector(fault_rate=1.5)


def test_reset_restarts_schedule():
    inj = FaultInjector(seed=2, fault_rate=0.5)
    first = [inj.inject("check_budget", {"budget_id": "B"}, BUDGET)[1] for _ in range(10)]
    inj.reset()
    assert first == [inj.inject("check_budget", {"budget_id": "B"}, BUDGET)[1] for _ in range(10)]


# ─── Replay ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("task_id", ["T01", "T12", "T17", "T20"])
def test_replay_reproduces_logged_episode(task_id, tmp_path):
    task = TASKS[task_id]
    env = ProcurementEnv(task, FaultInjector(seed=7, fault_rate=0.4))
    env.run_actions(task.reference_solution)
    path = tmp_path / "traj.jsonl"
    save_records(env.records, path)
    assert replay_records(task, load_records(path), seed=7, fault_rate=0.4) == []


def test_replay_detects_divergence():
    task = TASKS["T20"]
    env = ProcurementEnv(task, FaultInjector(seed=7, fault_rate=0.4))
    env.run_actions(task.reference_solution)
    assert replay_records(task, env.records, seed=8, fault_rate=0.4) != []


def test_replay_injector_feeds_back_exact_observations():
    task = TASKS["T19"]
    env = ProcurementEnv(task, FaultInjector(seed=3, fault_rate=0.5))
    env.run_actions(task.reference_solution)
    again = ProcurementEnv(task, ReplayInjector(env.records))
    again.run_actions(task.reference_solution)
    assert [r["observed_result"] for r in again.records] == [r["observed_result"] for r in env.records]
    assert [r["fault_injected"] for r in again.records] == [r["fault_injected"] for r in env.records]
