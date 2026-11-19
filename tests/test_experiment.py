import json
from pathlib import Path

import pytest

from experiments.run_experiment import load_config, run_batch
from src.evaluation.analysis import read_run, write_project_dashboard, write_report
from src.evaluation.dashboard import reliability_plot
from src.evaluation.metrics import summarize, verification_diagnostics


CONFIG = Path(__file__).resolve().parents[1] / "experiments/configs/phase7_smoke.json"


def test_verification_diagnostics_distinguish_selection_retry_and_provider_errors():
    steps = [
        dict(origin="agent", verify_decision=True, fault_injected="wrong_value",
             trigger_reason="schema_fail", verifier_verdict={"suspicious": True}),
        dict(origin="recovery", verify_decision=True, verifier_verdict={"suspicious": False}),
        dict(origin="agent", verify_decision=False, fault_injected="stale_value"),
        dict(origin="agent", verify_decision=True, trigger_reason="high_risk_tool",
             verifier_verdict={"suspicious": True}, verifier_error="provider error"),
    ]
    diagnostic = verification_diagnostics(steps)
    assert diagnostic["trigger_precision"] == diagnostic["trigger_recall"] == 0.5
    assert diagnostic["verdict_counts"] == {"tp": 1, "fn": 0, "fp": 0, "tn": 1}
    assert diagnostic["triggers"] == {"schema_fail": 1, "high_risk_tool": 1}


def test_dashboard_plot_preserves_boundaries_and_groups_identical_coordinates():
    summary = {
        "A": {"verifier_calls_per_action": 0, "success_rate": 1},
        "B": {"verifier_calls_per_action": 1.5, "success_rate": 0},
        "C": {"verifier_calls_per_action": 0, "success_rate": 1},
    }
    plot = reliability_plot(summary)
    assert plot.count('class="point ') == 2
    assert "left:0.000000%;bottom:100.000000%" in plot
    assert "left:100.000000%;bottom:0.000000%" in plot
    assert "A / C" in plot and ">1.50<" in plot
    assert "No agent actions" in reliability_plot({})


def test_project_archive_lists_runs_without_phase_groups(tmp_path):
    config = load_config(CONFIG)
    config.update(tasks=["T01"], seeds=[7], policies=["A"])
    for phase, directory in [(7, "output/phase7/offline run"), (8, "logs/phase8/pilot")]:
        config["phase"] = phase
        log = run_batch(config, tmp_path / directory, f"run-{phase}")
        write_report(log)
    dashboard = write_project_dashboard(tmp_path)
    html = dashboard.read_text(encoding="utf-8")
    assert dashboard == tmp_path / "output/dashboard.html"
    assert "<h2>Saved runs</h2>" in html
    assert "<h2>Phase" not in html
    assert 'href="phase7/offline%20run/dashboard.html"' in html
    assert 'href="../logs/phase8/pilot/dashboard.html"' in html
    assert html.count("Offline scripted run") == 2
    assert "Selected actions" in html and "Verifier calls" in html


def test_batch_rebuilds_dashboard_from_matched_jsonl(tmp_path):
    path = run_batch(load_config(CONFIG), tmp_path / "run", "test")
    header, episodes = read_run(path)
    assert header["run_id"] == "test"
    assert len(episodes) == 16
    for policy in "ABCD":
        pairs = {(ep["task_id"], ep["seed"]) for ep in episodes if ep["policy"] == policy}
        assert pairs == {("T01", 7), ("T01", 12), ("T11", 7), ("T11", 12)}
    for episode in episodes:
        assert len(episode["trajectory"]) == episode["result"]["tool_calls"]
    summary = write_report(path)
    assert summary["A"]["verifier_calls"] == 0
    assert summary["B"]["verify_triggered"] == summary["B"]["steps"]
    assert all(row["completion_rate"] == 1 for row in summary.values())
    dashboard = path.with_name("dashboard.html").read_text(encoding="utf-8")
    assert "Selected actions" in dashboard and "Verifier calls" in dashboard
    assert dashboard.count("<details>") == 16
    paired = json.loads(path.with_name("paired.json").read_text(encoding="utf-8"))
    assert paired["D"]["pairs"] == 4
    assert paired["D"]["calls_delta"] == -3
    assert write_report(path) == summary


def test_partial_log_keeps_planned_interrupted_and_failed_episodes(tmp_path):
    path = tmp_path / "events.jsonl"
    plan = [dict(episode_id=str(i), policy="A") for i in range(3)]
    events = [
        dict(event="run_started", schema_version=1, plan=plan),
        dict(event="episode_started", episode_id="0", goal="Test"),
        dict(event="episode_finished", episode_id="0", status="error", result={}),
        dict(event="episode_started", episode_id="1", goal="Test"),
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in events) + '{"event":', encoding="utf-8")
    _, episodes = read_run(path)
    assert [ep["status"] for ep in episodes] == ["error", "interrupted", "planned"]
    row = summarize(episodes)["A"]
    assert (row["planned"], row["completed"], row["errors"], row["incomplete"]) == (3, 0, 1, 2)
    assert row["success_rate"] == 0
    assert row["selection_rate"] is None


def test_config_rejects_duplicate_trials(tmp_path):
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["seeds"] = [7, 7]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate values in seeds"):
        load_config(path)


def test_batch_records_setup_errors_and_continues(tmp_path, monkeypatch):
    from experiments import run_experiment

    def unavailable(*args, **kwargs):
        raise RuntimeError("provider detail")

    monkeypatch.setattr(run_experiment, "make_llm", unavailable)
    config = load_config(CONFIG)
    config.update(tasks=["T01"], seeds=[7], policies=["A", "B"])
    log = run_batch(config, tmp_path / "error-run", "test")
    _, episodes = read_run(log)
    assert [episode["status"] for episode in episodes] == ["error", "error"]
    assert all(episode["result"] == {"error": "RuntimeError"} for episode in episodes)
    assert write_report(log)["B"]["completion_rate"] == 0


def test_batch_keeps_http_status_without_saving_provider_response(tmp_path, monkeypatch):
    from experiments import run_experiment

    class ProviderError(Exception):
        code = 503

    class Agent:
        def invoke(self, messages):
            raise ProviderError("private provider payload")

    monkeypatch.setattr(run_experiment, "make_llm", lambda *args, **kwargs: Agent())
    config = load_config(CONFIG)
    config.update(tasks=["T01"], seeds=[7], policies=["A"])
    log = run_batch(config, tmp_path / "http-error", "test")
    _, episodes = read_run(log)
    result = episodes[0]["result"]
    assert episodes[0]["status"] == "error"
    assert result["error"] == "ProviderError (HTTP 503 Service Unavailable)"
    assert result["error_details"] == {"http_status": 503, "reason": "Service Unavailable"}
    assert "private provider payload" not in log.read_text(encoding="utf-8")
    write_report(log)
    dashboard = log.with_name("dashboard.html").read_text(encoding="utf-8")
    assert "Run errors" in dashboard and "HTTP 503 Service Unavailable" in dashboard


def test_gemini_separates_agent_tools_and_verifier(monkeypatch):
    import sys
    from types import SimpleNamespace
    from src.agent.llm import make_llm, make_verifier_llm

    class FakeGemini:
        def __init__(self, **settings):
            self.settings = settings
            self.tools = None

        def bind_tools(self, tools):
            self.tools = tools
            return self

    monkeypatch.setenv("GEMINI_API_KEY", "offline-test")
    monkeypatch.setitem(sys.modules, "langchain_google_genai",
                        SimpleNamespace(ChatGoogleGenerativeAI=FakeGemini))
    agent = make_llm("gemini", model="agent")
    verifier = make_verifier_llm("gemini", "verifier")
    assert agent.tools and verifier.tools is None
    assert agent.settings["model"] == "agent"
    assert verifier.settings["model"] == "verifier"
