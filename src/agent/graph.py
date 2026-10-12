"""
graph.py — Phase 4
The LangGraph agent loop (plan Section 6). Every research-critical stage is its
own node so it is explicit and separately logged:

  START → init → agent ─┬─(tool call)→ tool_exec → fault_injection → policy_router → observe ─┐
                        │                                                                    │
                        └─(finish / no tool call / step limit)→ finalize → END   ← agent ←───┘

  init             builds the prompt from the task goal
  agent            LLM picks ONE structured tool call (or `finish`)
  tool_exec        runs the tool on the simulator → TRUE result (hidden from the agent)
  fault_injection  seeded injector → OBSERVED result
  policy_router    Policy A–D decision (verify? + trigger reason) — logged.
                   Phase 5 adds the self-verifier + recovery branch here.
  observe          returns ONLY the observed result to the agent; enforces the step limit
  finalize         deterministic oracle on the TRUE final state

The graph state holds only serialisable data; the environment, model and policy
are bound in a closure by build_graph().
"""
import json
import time
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from ..environment.env import ProcurementEnv
from ..evaluation.oracle import oracle_check
from ..policies.policies import should_verify
from .prompts import FINISH_TOOL, SYSTEM_PROMPT, task_message

DEFAULT_MAX_STEPS = 30


class AgentState(TypedDict, total=False):
    task_id: str
    goal: str
    messages: List[Any]
    step: int                         # agent tool calls executed so far
    max_steps: int
    latest_action: Optional[Dict[str, Any]]      # {"tool", "args", "id"}
    pending: Optional[Dict[str, Any]]            # record being built for the current step
    trajectory: List[Dict[str, Any]]             # completed step records (research log)
    done: bool
    done_reason: str                  # finish | gave_up | no_tool_call | max_steps
    final_summary: str
    llm_calls: int
    usage: Dict[str, int]             # input/output tokens across agent calls
    oracle_pass: bool
    oracle_diff: Dict[str, Any]


def _tool_content(observed: Any) -> str:
    return json.dumps(observed, default=str)


def _add_usage(usage: Dict[str, int], msg: AIMessage) -> Dict[str, int]:
    meta = getattr(msg, "usage_metadata", None) or {}
    out = dict(usage)
    out["input_tokens"] = out.get("input_tokens", 0) + int(meta.get("input_tokens", 0) or 0)
    out["output_tokens"] = out.get("output_tokens", 0) + int(meta.get("output_tokens", 0) or 0)
    return out


def build_graph(env: ProcurementEnv, llm, policy: str = "A", controller=None, cache=None):
    """Compile the agent graph for one episode on `env` under verification `policy`."""

    def init(state: AgentState) -> AgentState:
        return {
            "task_id": env.task.id,
            "goal": env.task.goal,
            "messages": [SystemMessage(SYSTEM_PROMPT), HumanMessage(task_message(env.task))],
            "step": 0,
            "trajectory": [],
            "done": False,
            "done_reason": "",
            "final_summary": "",
            "llm_calls": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "latest_action": None,
            "pending": None,
        }

    def agent(state: AgentState) -> AgentState:
        ai: AIMessage = llm.invoke(state["messages"])
        messages = state["messages"] + [ai]
        update: AgentState = {"llm_calls": state["llm_calls"] + 1, "usage": _add_usage(state["usage"], ai)}
        calls = list(getattr(ai, "tool_calls", None) or [])
        if not calls:
            text = ai.content if isinstance(ai.content, str) else json.dumps(ai.content, default=str)
            return {**update, "messages": messages, "done": True, "done_reason": "no_tool_call",
                    "final_summary": text, "latest_action": None}

        first, extra = calls[0], calls[1:]
        # Every tool_use must get a tool_result; only the first call is executed.
        for c in extra:
            messages.append(ToolMessage(content=_tool_content(
                {"error": "Only one tool call is executed per turn; this call was skipped."}),
                tool_call_id=c["id"]))
        if first["name"] == FINISH_TOOL:
            args = first.get("args") or {}
            status = args.get("status", "done")
            messages.append(ToolMessage(content=_tool_content({"ok": True}), tool_call_id=first["id"]))
            return {**update, "messages": messages, "done": True,
                    "done_reason": "gave_up" if status == "gave_up" else "finish",
                    "final_summary": str(args.get("summary", "")), "latest_action": None}
        action = {"tool": first["name"], "args": first.get("args") or {}, "id": first["id"]}
        return {**update, "messages": messages, "latest_action": action}

    def tool_exec(state: AgentState) -> AgentState:
        a = state["latest_action"]
        record = env.execute(a["tool"], a["args"], origin="agent")
        return {"pending": record}

    def fault_injection(state: AgentState) -> AgentState:
        record = env.apply_fault(state["pending"])
        return {"pending": record}

    def policy_router(state: AgentState) -> AgentState:
        r = dict(state["pending"])
        a = state["latest_action"]
        verify, reason = should_verify(policy=policy, action={"tool": a["tool"], "args": r["args"]},
                                       result=r["observed_result"], history=state["trajectory"],
                                       step=r["step"], controller=controller, cache=cache)
        r.update(verify_decision=bool(verify), trigger_reason=reason,
                 verifier_verdict=None, recovery_attempts=0)   # filled by Phase 5
        return {"pending": r}

    def observe(state: AgentState) -> AgentState:
        r = state["pending"]
        a = state["latest_action"]
        # The agent sees the OBSERVED result only — never the true result.
        msg = ToolMessage(content=_tool_content(r["observed_result"]), tool_call_id=a["id"])
        step = state["step"] + 1
        out: AgentState = {"messages": state["messages"] + [msg], "trajectory": state["trajectory"] + [r],
                           "step": step, "pending": None}
        if step >= state["max_steps"]:
            out.update(done=True, done_reason="max_steps")
        return out

    def finalize(state: AgentState) -> AgentState:
        passed, diff = oracle_check(env.true_state, env.task.expected_final_state, env.sim.initial_state)
        return {"oracle_pass": passed, "oracle_diff": diff}

    def after_agent(state: AgentState) -> str:
        return "finalize" if state.get("done") else "tool_exec"

    def after_observe(state: AgentState) -> str:
        return "finalize" if state.get("done") else "agent"

    g = StateGraph(AgentState)
    for name, fn in [("init", init), ("agent", agent), ("tool_exec", tool_exec),
                     ("fault_injection", fault_injection), ("policy_router", policy_router),
                     ("observe", observe), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "init")
    g.add_edge("init", "agent")
    g.add_conditional_edges("agent", after_agent, {"tool_exec": "tool_exec", "finalize": "finalize"})
    g.add_edge("tool_exec", "fault_injection")
    g.add_edge("fault_injection", "policy_router")
    g.add_edge("policy_router", "observe")
    g.add_conditional_edges("observe", after_observe, {"agent": "agent", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()


def run_episode(task, llm, policy: str = "A", seed: int = 0, fault_rate: float = 0.0,
                max_steps: int = DEFAULT_MAX_STEPS, injector=None, model_name: str = "",
                controller=None, cache=None) -> Dict[str, Any]:
    """
    Run one task end to end and return a summary + full trajectory.
    fault_rate == 0 and no injector → clean environment.
    """
    from ..faults.injector import FaultInjector
    if injector is None and fault_rate > 0:
        injector = FaultInjector(seed=seed, fault_rate=fault_rate)
    env = ProcurementEnv(task, injector=injector)
    graph = build_graph(env, llm, policy=policy, controller=controller, cache=cache)

    t0 = time.time()
    error = None
    try:
        # Each agent step visits 5 nodes; the limit is a hard backstop behind max_steps.
        final = graph.invoke({"max_steps": max_steps}, config={"recursion_limit": 6 * max_steps + 20})
    except Exception as e:  # noqa: BLE001 — an LLM/API failure must not lose the episode log
        error = f"{type(e).__name__}: {e}"
        passed, diff = oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)
        final = {"trajectory": env.records, "step": len(env.records), "done_reason": "error",
                 "final_summary": "", "llm_calls": None, "usage": {}, "oracle_pass": passed,
                 "oracle_diff": diff}

    traj = final["trajectory"]
    return {
        "task_id": task.id, "tier": task.tier, "family": task.family,
        "policy": policy, "seed": seed, "fault_rate": fault_rate, "model": model_name,
        "oracle_pass": final["oracle_pass"], "oracle_diff": final["oracle_diff"],
        "done_reason": final["done_reason"], "final_summary": final.get("final_summary", ""),
        "steps": final["step"], "llm_calls": final.get("llm_calls"), "usage": final.get("usage", {}),
        "faults_injected": sum(1 for r in traj if r.get("fault_injected")),
        "verify_triggered": sum(1 for r in traj if r.get("verify_decision")),
        "invalid_calls": sum(1 for r in traj if r.get("invalid_call")),
        "wall_time_s": round(time.time() - t0, 3), "error": error,
        "trajectory": traj,
    }
