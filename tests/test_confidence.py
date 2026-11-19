"""Action confidence stays separate from simulator inputs and observed results."""
import copy
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.agent import build_graph, load_episode, run_episode, save_episode, ScriptedChatModel
from src.agent.llm import tool_schemas
from src.agent.prompts import FINISH_SPEC, SYSTEM_PROMPT
from src.environment.env import ProcurementEnv
from src.environment.tasks import get_task
from src.environment.tools import TOOL_SPECS
from src.faults.replay import ReplayInjector, replay_records
from tests.test_agent import ListModel, call, FINISH, accepting_verifier
from tests.test_recovery import always_suspicious


def test_confidence_schema_is_agent_only_and_each_call_is_independent():
    before = copy.deepcopy(TOOL_SPECS)
    schemas = tool_schemas()
    for schema in schemas:
        tool = schema["function"]
        if tool["name"] == "finish":
            assert tool["parameters"] == FINISH_SPEC["parameters"]
            continue
        params = tool["parameters"]
        confidence = params["properties"]["_confidence"]
        assert confidence["type"] == "number"
        assert confidence["minimum"] == 0 and confidence["maximum"] == 1
        assert params["required"].count("_confidence") == 1
    schemas[0]["function"]["parameters"]["properties"]["_confidence"]["maximum"] = 50
    assert tool_schemas()[0]["function"]["parameters"]["properties"]["_confidence"]["maximum"] == 1
    assert TOOL_SPECS == before


def test_all_policies_collect_same_confidence_but_keep_their_own_timing():
    outcomes = {}
    for policy in "ABCD":
        agent = ListModel([
            call("check_budget", 0, budget_id="BUD-A", _confidence=0.9),
            call("check_budget", 1, budget_id="BUD-A", _confidence=0.2), FINISH])
        env = ProcurementEnv(get_task("T01"))
        output = build_graph(env, agent, policy=policy,
                             verifier_llm=accepting_verifier()).invoke({"max_steps": 5})
        records = output["trajectory"]
        assert [r["action_confidence"] for r in records] == [0.9, 0.2]
        assert all(r["confidence_source"] == "self_reported" for r in records)
        assert all(r["args"] == {"budget_id": "BUD-A"} and not r["invalid_call"] for r in records)
        assert all("_confidence" not in r["observed_result"] for r in records)
        assert output["messages"][0].content == SYSTEM_PROMPT
        assert output["llm_calls"] == agent.i == 3  # two actions and finish; no confidence call
        assert output["messages"][2].tool_calls[0]["args"]["_confidence"] == 0.9
        outcomes[policy] = [r["verify_decision"] for r in records]
        if policy == "D":
            assert records[1]["trigger_reason"] == "low_confidence"
    assert outcomes == {"A": [False, False], "B": [True, True],
                        "C": [True, False], "D": [False, True]}


@pytest.mark.parametrize("value,expected", [
    (0, 0.0), (1, 1.0), (0.3, 0.3), (None, None), (True, None),
    ("0.2", None), ([], None), ({}, None), (-0.1, None), (1.1, None),
    (float("nan"), None), (float("inf"), None), (-float("inf"), None),
])
def test_confidence_validation_and_json_roundtrip(value, expected, tmp_path):
    message = call("check_budget", budget_id="BUD-A", _confidence=value)
    result = run_episode(get_task("T01"), ListModel([message, FINISH]), policy="D",
                         verifier_llm=accepting_verifier())
    record = result["trajectory"][0]
    assert result["error"] is None and not record["invalid_call"]
    assert record["action_confidence"] == expected
    assert record["confidence_source"] == ("self_reported" if expected is not None else "unavailable")
    assert record["verify_decision"] == (expected is not None and expected < 0.6)
    assert record["args"] == {"budget_id": "BUD-A"}
    json.dumps(result, allow_nan=False)  # invalid metadata must not put NaN/Infinity in the log
    assert load_episode(save_episode(result, tmp_path)) == result


def test_missing_confidence_is_unavailable_for_existing_scripted_agents():
    task = get_task("T01")
    result = run_episode(task, ScriptedChatModel(task.reference_solution), policy="D",
                         verifier_llm=accepting_verifier())
    assert result["oracle_pass"]
    assert all(r["action_confidence"] is None and r["confidence_source"] == "unavailable"
               for r in result["trajectory"])
    assert not any(r["trigger_reason"] == "low_confidence" for r in result["trajectory"])


@pytest.mark.parametrize("reported,observed,expected", [(0.1, 1, True), (0.9, 0, False), (None, 0, False)])
def test_observation_cannot_overwrite_action_confidence(reported, observed, expected):
    task = get_task("T01")
    budget = ProcurementEnv(task).call("check_budget", {"budget_id": "BUD-A"})["observed_result"]
    budget["_confidence"] = observed
    injector = ReplayInjector([{"tool": "check_budget", "args": {"budget_id": "BUD-A"},
                                "observed_result": budget, "fault_injected": "wrong_value"}])
    agent = ListModel([call("check_budget", budget_id="BUD-A", _confidence=reported), FINISH])
    result = run_episode(task, agent, policy="D", injector=injector, verifier_llm=accepting_verifier())
    record = result["trajectory"][0]
    assert record["action_confidence"] == reported
    assert record["verify_decision"] is expected


def test_changing_confidence_does_not_change_fault_keys_or_replay():
    task = get_task("T01")
    runs = []
    for confidence in (0.1, 0.9):
        actions = copy.deepcopy(task.reference_solution)
        for action in actions:
            action["args"]["_confidence"] = confidence
        result = run_episode(task, ScriptedChatModel(actions), policy="D", seed=7, fault_rate=0.4,
                             verifier_llm=accepting_verifier())
        assert result["error"] is None
        assert replay_records(task, result["trajectory"], seed=7, fault_rate=0.4) == []
        runs.append([(r["args"], r["observed_result"], r["fault_injected"]) for r in result["trajectory"]])
    assert runs[0] == runs[1]


def test_retry_uses_clean_arguments_and_has_no_fabricated_confidence():
    message = call("check_budget", budget_id="BUD-A", _confidence=0.2)
    agent = ListModel([message, FINISH])
    env = ProcurementEnv(get_task("T01"))
    output = build_graph(env, agent, policy="D", verifier_llm=always_suspicious()).invoke({"max_steps": 5})
    original, retry = output["trajectory"]
    assert original["action_confidence"] == 0.2
    assert retry["action_confidence"] is None and retry["confidence_source"] == "unavailable"
    assert original["args"] == retry["args"] == {"budget_id": "BUD-A"}
    assert retry["recovery_of"] == original["step"]
    assert output["llm_calls"] == 2 and output["verifier_calls"] == 2
    assert message.tool_calls[0]["args"]["_confidence"] == 0.2  # original message was not mutated
    observations = [m for m in output["messages"] if isinstance(m, ToolMessage)]
    assert "_confidence" not in json.loads(observations[0].content)


def test_stripping_confidence_does_not_hide_other_invalid_arguments():
    agent = ListModel([call("check_budget", budget_id="BUD-A", _confidence=0.2, unexpected=1), FINISH])
    result = run_episode(get_task("T01"), agent)
    record = result["trajectory"][0]
    assert record["invalid_call"] and record["action_confidence"] == 0.2
    assert record["args"] == {"budget_id": "BUD-A", "unexpected": 1}
