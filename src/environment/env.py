"""
env.py — Phase 1/3
ProcurementEnv: the one place where a tool call is executed.

    tool call → simulator (TRUE result) → fault injector (OBSERVED result) → step record

Every runner (scripted reference replay, LangGraph agent, experiment harness)
goes through ProcurementEnv.call(), so true vs observed results are always
logged the same way and the simulator clock always advances once per call.
"""
import copy
from typing import Any, Dict, List, Optional

from .simulator import ProcurementSimulator
from .tasks import Task
from .tools import execute_tool, tool_risk, validate_args


class ProcurementEnv:
    def __init__(self, task: Task, injector=None):
        self.task     = task
        self.injector = injector          # None → clean environment
        self.sim      = ProcurementSimulator()
        self.sim.load(task.build_state())
        self.records: List[Dict[str, Any]] = []

    def reset(self):
        self.sim.reset()
        self.records = []
        if self.injector is not None:
            self.injector.reset()

    @property
    def true_state(self):
        return self.sim.state

    def execute(self, tool: str, args: Optional[Dict[str, Any]] = None, origin: str = "agent") -> Dict[str, Any]:
        """
        Stage 1 — run the tool on the simulator and return a partial record with the
        TRUE result only. Advances the simulator clock. Call apply_fault() next.
        """
        args = copy.deepcopy(args or {})
        step = self.sim.state.step
        clean_args, err = validate_args(tool, args)
        if err:
            # Invalid call (unknown tool / bad args): never touches state
            true_result = {"error": err}
        else:
            true_result = execute_tool(self.sim, tool, clean_args)
        self.sim.advance_step()
        return {
            "step":         step,
            "tool":         tool,
            "args":         clean_args if not err else args,
            "risk":         tool_risk(tool),
            "origin":       origin,
            "true_result":  true_result,
            "invalid_call": bool(err),
        }

    def apply_fault(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stage 2 — pass the true result through the fault injector to produce the
        OBSERVED result, then log the completed record. Invalid calls are never faulted.
        """
        if record["invalid_call"] or self.injector is None:
            observed, fault = copy.deepcopy(record["true_result"]), None
        else:
            observed, fault = self.injector.inject(record["tool"], record["args"], record["true_result"])
        record = dict(record, observed_result=observed, fault_injected=fault)
        self.records.append(record)
        return record

    def call(self, tool: str, args: Optional[Dict[str, Any]] = None, origin: str = "agent") -> Dict[str, Any]:
        """
        Execute one tool call end to end (execute → apply_fault).
        origin: "agent" for normal actions, "recovery" for verifier/recovery re-calls (Phase 5).
        Returns the step record; record["observed_result"] is what the agent may see.
        """
        return self.apply_fault(self.execute(tool, args, origin))

    def run_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run a fixed list of {"tool", "args"} actions (reference trajectories, replay)."""
        return [self.call(a["tool"], a.get("args", {})) for a in actions]
