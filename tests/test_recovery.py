"""Phase 5 end-to-end checks, driven entirely by offline models."""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent import build_graph, run_episode, save_episode, load_episode, make_llm
from src.environment.env import ProcurementEnv
from src.environment.tasks import get_task, load_tasks
from src.faults.injector import FaultInjector
from src.faults.replay import ReplayInjector, replay_records
from src.verifier.verifier import ScriptedVerifier
from tests.test_agent import ListModel, call, FINISH


def budget_timeout():
    return ReplayInjector([{"tool": "check_budget", "args": {"budget_id": "BUD-A"},
                            "observed_result": {"error": "TIMEOUT", "timeout": True},
                            "fault_injected": "timeout"}])


def budget_agent():
    return ListModel([call("check_budget", budget_id="BUD-A"), FINISH])


def always_suspicious():
    return ListModel([AIMessage(content='{"suspicious": true, "reason": "Unresolved conflict."}',
                               usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})])


def test_graph_exposes_verifier_recovery_and_replan_nodes():
    graph = build_graph(ProcurementEnv(get_task("T01")), budget_agent(), policy="B",
                        verifier_llm=ScriptedVerifier())
    assert {"verifier", "recovery", "replan"} <= set(graph.get_graph().nodes)


def test_verification_policy_requires_an_explicit_verifier():
    with pytest.raises(ValueError, match="verifier_llm"):
        run_episode(get_task("T01"), budget_agent(), policy="B")


def test_policy_a_never_calls_verifier_or_retries():
    verifier = always_suspicious()
    result = run_episode(get_task("T01"), budget_agent(), policy="A",
                         injector=budget_timeout(), verifier_llm=verifier)
    assert verifier.i == 0
    assert result["verifier_calls"] == result["recovery_attempts"] == 0
    assert len(result["trajectory"]) == 1


@pytest.mark.parametrize("policy", ["B", "C", "D"])
def test_each_verifying_policy_retries_once_and_uses_only_retry_observation(policy):
    env = ProcurementEnv(get_task("T01"), budget_timeout())
    output = build_graph(env, budget_agent(), policy=policy, verifier_llm=ScriptedVerifier()).invoke({"max_steps": 3})
    original, retry = output["trajectory"]
    assert original["verifier_verdict"]["suspicious"]
    assert original["recovery_attempts"] == 1 and original["recovered"]
    assert not retry["verifier_verdict"]["suspicious"]
    assert retry["origin"] == "recovery" and retry["recovery_of"] == original["step"]
    assert original["tool"] == retry["tool"] and original["args"] == retry["args"]
    tool_messages = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert json.loads(tool_messages[0].content) == retry["observed_result"]
    assert output["step"] == 1 and env.true_state.step == 2


def test_repeated_suspicion_stops_at_one_retry_and_replans_with_observations():
    env = ProcurementEnv(get_task("T01"), budget_timeout())
    output = build_graph(env, budget_agent(), policy="B", verifier_llm=always_suspicious()).invoke({"max_steps": 3})
    original, retry = output["trajectory"]
    assert original["unrecovered_fault"] and original["replan_requested"]
    assert not original["recovered"] and original["recovery_attempts"] == 1
    assert output["verifier_calls"] == 2
    concern = [m.content for m in output["messages"] if isinstance(m, HumanMessage)][-1]
    assert "Replan" in concern and "Unresolved conflict" in concern
    assert "true_result" not in concern and "fault_injected" not in concern
    assert retry["observed_result"] == original["final_result_used"]


def test_invalid_verdict_requests_replan_without_repeating_a_write():
    task = get_task("T01")
    agent = ListModel([call("create_purchase_order", project_id="PROJ-A", quote_id="Q1", quantity=10), FINISH])
    result = run_episode(task, agent, policy="B", verifier_llm=ListModel([AIMessage(content="null")]))
    assert result["recovery_attempts"] == 0 and result["tool_calls"] == 1
    assert result["unrecovered_steps"] == 1
    assert result["trajectory"][0]["verifier_error"]


def test_verifier_provider_outage_preserves_episode_and_does_not_retry():
    class Offline:
        def invoke(self, messages):
            raise ConnectionError("verifier offline")
    result = run_episode(get_task("T01"), budget_agent(), policy="B", verifier_llm=Offline())
    assert result["done_reason"] == "finish" and result["error"] is None
    assert result["trajectory"][0]["verifier_error"] == "ConnectionError: verifier offline"
    assert result["verifier_calls"] == 1 and result["recovery_attempts"] == 0


def test_timeout_after_write_keeps_both_effects_and_oracle_detects_duplicate():
    task = get_task("T01")
    injector = ReplayInjector([{"tool": "create_purchase_order",
                               "args": {"project_id": "PROJ-A", "quote_id": "Q1", "quantity": 10},
                               "observed_result": {"error": "TIMEOUT", "timeout": True},
                               "fault_injected": "timeout"}])
    result = run_episode(task, make_llm("scripted", task=task), policy="B", injector=injector,
                         verifier_llm=ScriptedVerifier())
    writes = [r for r in result["trajectory"] if r["tool"] == "create_purchase_order"]
    assert [r["true_result"]["po_id"] for r in writes] == ["PO-0001", "PO-0002"]
    assert result["recovery_attempts"] == 1 and result["recovered_steps"] == 1
    assert not result["oracle_pass"] and not result["oracle_diff"]["no_duplicate_orders"]["pass"]


def test_cost_accounting_and_roundtrip_include_retry_checks(tmp_path):
    agent = ListModel([AIMessage(content="", tool_calls=[{"name": "check_budget", "args": {"budget_id": "BUD-A"},
                                                        "id": "budget"}],
                                 usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}), FINISH])
    result = run_episode(get_task("T01"), agent, policy="B", verifier_llm=always_suspicious())
    assert result["steps"] == 1 and result["tool_calls"] == 2
    assert result["llm_calls"] == 2 and result["verifier_calls"] == 2 and result["total_llm_calls"] == 4
    assert result["usage"] == {"input_tokens": 23, "output_tokens": 12}
    assert result["agent_usage"] == {"input_tokens": 3, "output_tokens": 2}
    assert result["verifier_usage"] == {"input_tokens": 20, "output_tokens": 10}
    assert result["verify_triggered"] == 1
    assert load_episode(save_episode(result, tmp_path)) == result


def test_recovery_logs_replay_with_seeded_faults():
    task = get_task("T01")
    injector = FaultInjector(seed=7, fault_rate=1, fault_types=["timeout"])
    result = run_episode(task, make_llm("scripted", task=task), policy="B", injector=injector,
                         seed=7, fault_rate=1, verifier_llm=ScriptedVerifier())
    assert result["recovery_attempts"] == len(task.reference_solution)
    assert replay_records(task, result["trajectory"], 7, 1, fault_types=["timeout"]) == []


def test_step_limit_bounds_suspicious_loop_and_keeps_all_calls():
    looping = ListModel([call("check_budget", budget_id="BUD-A")])
    result = run_episode(get_task("T01"), looping, policy="B", max_steps=3,
                         verifier_llm=always_suspicious())
    assert result["done_reason"] == "max_steps" and result["steps"] == 3
    assert result["tool_calls"] == result["verifier_calls"] == 6
    assert result["unrecovered_steps"] == result["recovery_attempts"] == 3


def test_agent_failure_after_retry_keeps_verdicts_and_costs():
    class FailingAgent:
        def invoke(self, messages):
            if any(isinstance(m, AIMessage) for m in messages):
                raise ConnectionError("agent offline")
            return call("check_budget", budget_id="BUD-A")
    result = run_episode(get_task("T01"), FailingAgent(), policy="B", injector=budget_timeout(),
                         verifier_llm=ScriptedVerifier())
    assert result["done_reason"] == "error" and result["llm_calls"] == 2
    assert result["tool_calls"] == 2 and result["verifier_calls"] == 2
    assert all(r["verifier_verdict"] is not None for r in result["trajectory"])


def test_fixed_schedule_counts_agent_actions_not_extra_tool_calls():
    action = call("check_budget", budget_id="BUD-A")
    agent = ListModel([action, action, action, action, FINISH])
    result = run_episode(get_task("T01"), agent, policy="C", verifier_llm=always_suspicious())
    originals = [r for r in result["trajectory"] if r["origin"] == "agent"]
    assert [r["verify_decision"] for r in originals] == [True, False, False, True]
    assert [r["step"] for r in originals] == [0, 2, 3, 4]


@pytest.mark.parametrize("max_steps", [0, -1, None, True])
def test_invalid_step_limits_rejected(max_steps):
    with pytest.raises(ValueError, match="max_steps"):
        run_episode(get_task("T01"), budget_agent(), max_steps=max_steps)


@pytest.mark.parametrize("policy", ["A", "B", "C", "D"])
def test_all_clean_tasks_pass_with_offline_verifier(policy):
    for task in load_tasks():
        result = run_episode(task, make_llm("scripted", task=task), policy=policy,
                             verifier_llm=ScriptedVerifier())
        assert result["oracle_pass"] and result["error"] is None, task.id
        assert result["recovery_attempts"] == 0


def test_demo_recovery_changes_the_agents_choice_and_true_outcome():
    from scripts.demo_recovery import run_demo
    unverified, verified = run_demo("A"), run_demo("B")
    assert not unverified["oracle_pass"] and verified["oracle_pass"]
    assert verified["recovered_steps"] == verified["recovery_attempts"] == 1
    assert unverified["trajectory"][0]["observed_result"] == verified["trajectory"][0]["observed_result"]
    before = next(r for r in unverified["trajectory"] if r["tool"] == "create_purchase_order")
    after = next(r for r in verified["trajectory"] if r["tool"] == "create_purchase_order")
    assert before["args"]["quote_id"] == "QO1" and after["args"]["quote_id"] == "QO2"


def test_runner_wires_the_verifier_and_saves_actual_call_counts(tmp_path, capsys):
    from run_agent import main
    assert main(["--task", "T01", "--provider", "scripted", "--policy", "B",
                 "--log-dir", str(tmp_path)]) == 0
    result = load_episode(next(tmp_path.glob("*.jsonl")))
    assert result["oracle_pass"]
    assert result["verifier_model"] == "scripted-verifier"
    assert result["verifier_calls"] == result["steps"] == 5
    assert "not an LLM evaluation" in capsys.readouterr().out
