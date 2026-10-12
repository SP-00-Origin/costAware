"""Phase 4 — LangGraph agent loop (driven by deterministic stand-in models; no API key needed)."""
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.agent import build_graph, run_episode, save_episode, load_episode, make_llm, ScriptedChatModel
from src.agent.llm import tool_schemas
from src.environment.env import ProcurementEnv
from src.environment.tasks import load_tasks
from src.environment.tools import TOOL_SPECS
from src.faults.injector import FaultInjector
from src.faults.replay import replay_records

TASKS = {t.id: t for t in load_tasks()}


class ListModel:
    """Returns a fixed list of AIMessages, one per turn (repeats the last one forever)."""
    def __init__(self, turns):
        self.turns = turns
        self.i = 0

    def bind_tools(self, *a, **k):
        return self

    def invoke(self, messages, **k):
        msg = self.turns[min(self.i, len(self.turns) - 1)]
        self.i += 1
        return msg


def call(name, i=0, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


FINISH = call("finish", 99, status="done", summary="ok")


# ─── Structure ───────────────────────────────────────────────────────────────

def test_graph_has_explicit_research_nodes():
    g = build_graph(ProcurementEnv(TASKS["T01"]), ScriptedChatModel([]))
    nodes = set(g.get_graph().nodes)
    assert {"init", "agent", "tool_exec", "fault_injection", "policy_router", "observe", "finalize"} <= nodes


def test_tool_schemas_cover_registry_plus_finish():
    names = [s["function"]["name"] for s in tool_schemas()]
    assert set(names) == set(TOOL_SPECS) | {"finish"}


# ─── Clean environment: the agent loop completes every task ─────────────────

@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_scripted_agent_passes_every_clean_task(task_id):
    task = TASKS[task_id]
    res = run_episode(task, make_llm("scripted", task=task))
    assert res["oracle_pass"], res["oracle_diff"]
    assert res["done_reason"] == "finish"
    assert res["steps"] == len(task.reference_solution)
    assert res["faults_injected"] == 0 and res["error"] is None


# ─── Termination ─────────────────────────────────────────────────────────────

def test_step_limit_stops_a_looping_agent():
    looping = ListModel([call("check_budget", budget_id="BUD-A")])
    res = run_episode(TASKS["T01"], looping, max_steps=7)
    assert res["done_reason"] == "max_steps" and res["steps"] == 7
    assert res["oracle_pass"] is False


def test_finish_ends_episode_immediately():
    res = run_episode(TASKS["T01"], ListModel([FINISH]))
    assert res["done_reason"] == "finish" and res["steps"] == 0


def test_gave_up_is_recorded():
    res = run_episode(TASKS["T01"], ListModel([call("finish", status="gave_up", summary="stuck")]))
    assert res["done_reason"] == "gave_up" and res["final_summary"] == "stuck"


def test_plain_text_answer_counts_as_done():
    res = run_episode(TASKS["T01"], ListModel([AIMessage(content="All done!")]))
    assert res["done_reason"] == "no_tool_call" and res["final_summary"] == "All done!"


# ─── Robustness ──────────────────────────────────────────────────────────────

def test_invalid_tool_and_bad_args_become_observations():
    model = ListModel([call("drop_database", 0), call("create_purchase_order", 1, project_id="PROJ-A"),
                       FINISH])
    res = run_episode(TASKS["T01"], model)
    assert res["steps"] == 2 and res["invalid_calls"] == 2
    assert all("error" in r["observed_result"] for r in res["trajectory"])
    assert res["done_reason"] == "finish"


def test_only_first_of_parallel_calls_runs_and_all_get_results():
    env = ProcurementEnv(TASKS["T01"])
    two = AIMessage(content="", tool_calls=[
        {"name": "check_budget", "args": {"budget_id": "BUD-A"}, "id": "a"},
        {"name": "create_purchase_order", "args": {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 10},
         "id": "b"}])
    out = build_graph(env, ListModel([two, FINISH])).invoke({"max_steps": 10})
    assert [r["tool"] for r in out["trajectory"]] == ["check_budget"]
    assert env.true_state.orders == {}                       # skipped write never happened
    answered = {m.tool_call_id for m in out["messages"] if isinstance(m, ToolMessage)}
    assert {"a", "b"} <= answered


def test_every_tool_call_is_answered_in_order():
    """Anthropic requires each tool_use to be followed by its tool_result."""
    task = TASKS["T16"]
    env = ProcurementEnv(task, FaultInjector(seed=1, fault_rate=0.5))
    out = build_graph(env, make_llm("scripted", task=task)).invoke({"max_steps": 40})
    msgs = out["messages"]
    for i, m in enumerate(msgs):
        if isinstance(m, AIMessage) and m.tool_calls:
            ids = [c["id"] for c in m.tool_calls]
            following = [x.tool_call_id for x in msgs[i + 1:i + 1 + len(ids)] if isinstance(x, ToolMessage)]
            assert following == ids


def test_llm_exception_does_not_lose_the_episode():
    class Boom:
        def bind_tools(self, *a, **k): return self
        def invoke(self, *a, **k): raise ConnectionError("API down")
    res = run_episode(TASKS["T01"], Boom())
    assert res["done_reason"] == "error" and "API down" in res["error"] and res["oracle_pass"] is False


def test_anthropic_provider_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        make_llm("anthropic")


# ─── Information boundary: agent sees observed, never true ──────────────────

def test_agent_only_sees_observed_results():
    task = TASKS["T19"]
    env = ProcurementEnv(task, FaultInjector(seed=4, fault_rate=0.6))
    out = build_graph(env, make_llm("scripted", task=task)).invoke({"max_steps": 40})
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)][:len(out["trajectory"])]  # drop finish ack
    faulted = [r for r in out["trajectory"] if r["fault_injected"]]
    assert faulted, "expected some faults at rate 0.6"
    for r, m in zip(out["trajectory"], tool_msgs):
        assert json.loads(m.content) == r["observed_result"]
    for r in faulted:
        assert r["observed_result"] != r["true_result"]


# ─── Policy decisions are logged per step ───────────────────────────────────

@pytest.mark.parametrize("policy,expect", [("A", lambda r: False), ("B", lambda r: True),
                                           ("C", lambda r: r["step"] % 3 == 0),
                                           ("D", None)])
def test_policy_router_logs_decisions(policy, expect):
    task = TASKS["T07"]
    res = run_episode(task, make_llm("scripted", task=task), policy=policy)
    for r in res["trajectory"]:
        assert "verify_decision" in r and "trigger_reason" in r
        if expect:
            assert r["verify_decision"] == expect(r)
        else:
            if r["risk"] == "high":
                assert r["verify_decision"] and r["trigger_reason"] == "high_risk_tool"


def test_faults_are_identical_across_policies():
    """Same task + seed → same faults on the same actions, whatever the policy."""
    task = TASKS["T20"]
    runs = {p: run_episode(task, make_llm("scripted", task=task), policy=p, seed=6, fault_rate=0.3)
            for p in "ABCD"}
    sig = {p: [(r["tool"], r["fault_injected"]) for r in res["trajectory"]] for p, res in runs.items()}
    assert sig["A"] == sig["B"] == sig["C"] == sig["D"]


# ─── Inspectable + reproducible trajectories ────────────────────────────────

def test_trajectory_roundtrip_and_replay(tmp_path):
    task = TASKS["T17"]
    res = run_episode(task, make_llm("scripted", task=task), policy="D", seed=2, fault_rate=0.4)
    path = save_episode(res, tmp_path)
    back = load_episode(path)
    assert back["oracle_pass"] == res["oracle_pass"] and len(back["trajectory"]) == res["steps"]
    for r in back["trajectory"]:
        assert {"true_result", "observed_result", "fault_injected", "verify_decision", "trigger_reason"} <= set(r)
    assert replay_records(task, back["trajectory"], seed=2, fault_rate=0.4) == []
