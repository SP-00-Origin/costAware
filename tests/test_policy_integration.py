"""Configured A–D runs keep shared execution/recovery rules and reproducible logs."""
import copy

import pytest

from scripts.demo_policies import main, run_comparison
from src.agent import build_graph, load_episode, run_episode, save_episode
from src.environment.env import ProcurementEnv
from src.environment.tasks import get_task
from src.faults.replay import replay_records
from tests.test_agent import ListModel, call, FINISH, accepting_verifier
from tests.test_recovery import always_suspicious


def test_custom_c_interval_counts_agent_actions_even_with_retries():
    agent = ListModel([call("check_budget", i, budget_id="BUD-A") for i in range(4)] + [FINISH])
    result = run_episode(get_task("T01"), agent, policy="C", policy_config={"interval": 2},
                         verifier_llm=always_suspicious())
    actions = [r for r in result["trajectory"] if r["origin"] == "agent"]
    assert [r["agent_step"] for r in actions if r["verify_decision"]] == [0, 2]
    assert result["steps"] == 4 and result["tool_calls"] == 6
    assert result["verify_triggered"] == 2 and result["verifier_calls"] == 4
    assert result["recovery_attempts"] == 2
    assert result["policy_config"] == {"interval": 2, "confidence_threshold": 0.6}


@pytest.mark.parametrize("threshold,expected", [(0.2, False), (0.6, False), (0.9, True)])
def test_custom_d_threshold_reaches_router(threshold, expected):
    agent = ListModel([call("check_budget", budget_id="BUD-A", _confidence=0.6), FINISH])
    result = run_episode(get_task("T01"), agent, policy="D",
                         policy_config={"confidence_threshold": threshold}, verifier_llm=accepting_verifier())
    assert result["trajectory"][0]["verify_decision"] is expected
    assert result["verifier_calls"] == int(expected)
    assert result["policy_config"] == {"interval": 3, "confidence_threshold": threshold}


def test_compiled_graph_copies_settings_before_caller_can_change_them():
    config = {"interval": 2}
    agent = ListModel([call("check_budget", i, budget_id="BUD-A") for i in range(3)] + [FINISH])
    graph = build_graph(ProcurementEnv(get_task("T01")), agent, policy="C",
                        verifier_llm=accepting_verifier(), policy_config=config)
    config["interval"] = 1
    result = graph.invoke({"max_steps": 5})
    assert [r["verify_decision"] for r in result["trajectory"]] == [True, False, True]


@pytest.mark.parametrize("config", [{"interval": 0}, {"confidence_threshold": float("nan")},
                                   {"intervall": 2}, []])
@pytest.mark.parametrize("entry", ["build_graph", "run_episode"])
def test_invalid_config_rejected_before_actions(entry, config):
    agent = ListModel([FINISH])
    env = ProcurementEnv(get_task("T01"))
    with pytest.raises(ValueError):
        if entry == "build_graph":
            build_graph(env, agent, policy_config=config)
        else:
            run_episode(env.task, agent, policy_config=config)
    assert agent.i == 0 and env.records == []


def test_unknown_policy_is_rejected_even_if_agent_would_finish_immediately():
    agent = ListModel([FINISH])
    with pytest.raises(ValueError, match="Unknown policy"):
        run_episode(get_task("T01"), agent, policy="typo", verifier_llm=accepting_verifier())
    assert agent.i == 0


def test_resolved_settings_survive_failed_run_and_log_roundtrip(tmp_path):
    class OfflineAgent:
        def invoke(self, messages):
            raise ConnectionError("offline in test")

    config = {"interval": 2, "confidence_threshold": 0.8}
    result = run_episode(get_task("T01"), OfflineAgent(), policy="D", policy_config=config,
                         verifier_llm=accepting_verifier(), max_steps=7)
    config["interval"] = 9
    assert result["done_reason"] == "error"
    assert result["policy_config"] == {"interval": 2, "confidence_threshold": 0.8}
    assert result["max_steps"] == 7
    assert load_episode(save_episode(result, tmp_path)) == result


@pytest.mark.parametrize("task_id", ["T01", "T11", "T20"])
def test_clean_demo_uses_identical_inputs_and_fresh_runs(task_id):
    config = {"interval": 2, "confidence_threshold": 0.8}
    runs = run_comparison(task_id, seed=11, fault_rate=0, policy_config=config)
    assert list(runs) == list("ABCD")
    for result in runs.values():
        assert result["oracle_pass"] and result["error"] is None
        assert result["task_id"] == task_id and result["seed"] == 11 and result["fault_rate"] == 0
        assert result["model"] == "scripted-reference" and result["verifier_model"] == "scripted-verifier"
        assert result["policy_config"] == config
        assert result["max_steps"] == 30
        assert result["recovery_attempts"] == 0
    assert runs["A"]["verifier_calls"] == 0
    assert runs["B"]["verifier_calls"] == runs["B"]["steps"]
    assert runs["C"]["verify_triggered"] == (runs["C"]["steps"] + 1) // 2
    assert config == {"interval": 2, "confidence_threshold": 0.8}
    runs["A"]["policy_config"]["interval"] = 9
    assert runs["B"]["policy_config"] == config


def test_faulted_demo_is_repeatable_and_each_policy_replays():
    first = run_comparison("T01", seed=7, fault_rate=1)
    second = run_comparison("T01", seed=7, fault_rate=1)
    initial = first["A"]["trajectory"][0]
    for policy in "ABCD":
        result = first[policy]
        assert result["error"] is None
        assert result["trajectory"][0]["observed_result"] == initial["observed_result"]
        assert replay_records(get_task("T01"), result["trajectory"], seed=7, fault_rate=1) == []
        for run in (first, second):
            records = run[policy]["trajectory"]
            run[policy]["signature"] = [
                (r["tool"], r["args"], r["observed_result"], r["fault_injected"],
                 r["verify_decision"], r["trigger_reason"], r["origin"]) for r in records]
        assert first[policy]["signature"] == second[policy]["signature"]
        assert first[policy]["oracle_pass"] == second[policy]["oracle_pass"]


def test_demo_command_saves_four_runs_with_resolved_settings(tmp_path, capsys):
    code = main(["--task", "T01", "--seed", "4", "--fault-rate", "0", "--interval", "2",
                 "--confidence-threshold", "0.8", "--max-steps", "12", "--log-dir", str(tmp_path)])
    assert code == 0
    logs = sorted(tmp_path.glob("*.jsonl"))
    assert len(logs) == 4
    results = [load_episode(path) for path in logs]
    assert {r["policy"] for r in results} == set("ABCD")
    assert all(r["policy_config"] == {"interval": 2, "confidence_threshold": 0.8} for r in results)
    assert all(r["seed"] == 4 and r["max_steps"] == 12 and r["oracle_pass"] for r in results)
    output = capsys.readouterr().out
    assert "no API calls" in output and "confidence is unavailable" in output


@pytest.mark.parametrize("args", [
    ["--task", "missing"], ["--interval", "0"], ["--confidence-threshold", "nan"],
    ["--fault-rate", "nan"], ["--fault-rate", "-0.1"], ["--max-steps", "0"],
])
def test_demo_rejects_invalid_inputs_without_writing_logs(args, tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(args + ["--log-dir", str(tmp_path)])
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_oracle_failure_is_a_recorded_outcome_not_a_demo_runtime_error(tmp_path, capsys):
    assert main(["--max-steps", "1", "--fault-rate", "0", "--log-dir", str(tmp_path)]) == 0
    assert "FAIL" in capsys.readouterr().out
    assert all(not load_episode(path)["oracle_pass"] for path in tmp_path.glob("*.jsonl"))


def test_demo_returns_failure_for_runtime_error(monkeypatch, tmp_path, capsys):
    results = copy.deepcopy(run_comparison(fault_rate=0))
    results["B"]["error"] = "offline test failure"
    monkeypatch.setattr("scripts.demo_policies.run_comparison", lambda *args: results)
    assert main(["--log-dir", str(tmp_path)]) == 1
    assert "Runtime error: offline test failure" in capsys.readouterr().out
