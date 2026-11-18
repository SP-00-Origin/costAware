"""Offline Phase 5 demo: wrong budget → suspicious → retry → oracle PASS.

Run: python scripts/demo_recovery.py
Both models are deterministic stand-ins. This demonstrates the recovery plumbing,
not measured LLM reliability. Policy A sees the same wrong initial observation.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, ToolMessage

from src.agent import run_episode, format_episode, save_episode
from src.environment.tasks import get_task
from src.faults.replay import ReplayInjector


class BudgetDemoAgent:
    """Choose a supplier from the observed budget, then release its order."""
    def invoke(self, messages):
        turn = sum(isinstance(message, AIMessage) for message in messages)
        if turn == 0:
            name, args = "check_budget", {"budget_id": "BUD-K"}
        elif turn == 1:
            results = [message for message in messages if isinstance(message, ToolMessage)]
            budget = json.loads(results[-1].content)
            quote = "QO1" if budget["remaining"] >= 12000 else "QO2"
            name, args = "create_purchase_order", {"project_id": "PROJ-K", "quote_id": quote, "quantity": 20}
        elif turn == 2:
            name, args = "release_order", {"po_id": "PO-0001"}
        else:
            name, args = "finish", {"status": "done", "summary": "Budget demo finished."}
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"demo_{turn}"}])


class BudgetDemoVerifier:
    """Check arithmetic in observed budget fields; never reads the environment."""
    def invoke(self, messages):
        evidence = json.loads(messages[-1].content)
        suspicious = False
        if evidence["action"]["tool"] == "check_budget":
            result = evidence["observed_result"]
            remaining = result["allocated"] - result["spent"] - result["reserved"]
            suspicious = abs(remaining - result["remaining"]) > 0.01
        reason = "Budget fields do not add up." if suspicious else "No conflict in the demo evidence."
        return AIMessage(content=json.dumps({"suspicious": suspicious, "reason": reason}))


def run_demo(policy="B"):
    fault = {"tool": "check_budget", "args": {"budget_id": "BUD-K"},
             "observed_result": {"id": "BUD-K", "allocated": 20000.0, "spent": 10000.0,
                                 "reserved": 0.0, "remaining": 20000.0},
             "fault_injected": "wrong_value"}
    result = run_episode(get_task("T11"), BudgetDemoAgent(), policy=policy,
                         injector=ReplayInjector([fault]), verifier_llm=BudgetDemoVerifier(),
                         model_name="scripted-budget-demo", verifier_model_name="scripted-budget-verifier")
    result["fault_source"] = "fixed replay: first BUD-K remaining value is 20000 instead of 10000"
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Offline recovery demonstration — deterministic stand-ins, no API calls.")
    results = {}
    for policy in ("A", "B"):
        result = run_demo(policy)
        results[policy] = result
        print(format_episode(result, show_results=True))
        print(f"Log: {save_episode(result, Path('logs') / 'phase5_demo')}")
    recovered = results["B"]
    return 0 if (not results["A"]["oracle_pass"] and recovered["oracle_pass"]
                 and recovered["recovered_steps"] == 1 and recovered["error"] is None) else 1


if __name__ == "__main__":
    sys.exit(main())
