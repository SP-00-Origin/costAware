"""
graph.py — Phases 4–5
The LangGraph agent loop (plan Section 6). Every research-critical stage is its
own node so it is explicit and separately logged:

  init → agent → tool_exec → fault_injection → policy_router
  policy_router → observe (skip) or verifier (verify)
  verifier → observe (OK), recovery → verifier (one retry), or replan → observe
  observe → agent (continue) or finalize (step limit); finish → finalize → END

  init             builds the prompt from the task goal
  agent            LLM picks ONE structured tool call (or `finish`)
  tool_exec        runs the tool on the simulator → TRUE result (hidden from the agent)
  fault_injection  seeded injector → OBSERVED result
  policy_router    Policy A–D decision: skip or verify
  verifier         checks observed evidence; suspicious results get one retry
  recovery         re-calls the tool, then returns to verifier
  replan           flags an unresolved concern for the next agent turn
  observe          returns ONLY the observed result to the agent; enforces the step limit
  finalize         deterministic oracle on the TRUE final state

The graph state holds only serialisable data; the environment, model and policy
are bound in a closure by build_graph().
"""
import copy
import json
import time
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from ..environment.env import ProcurementEnv
from ..environment.tools import HIGH_RISK_TOOLS, MEDIUM_RISK_TOOLS
from ..evaluation.oracle import oracle_check
from ..policies.config import validate_policy_config
from ..policies.policies import parse_confidence, should_verify
from ..provider_errors import error_details
from ..verifier.verifier import observation_history, verify_step
from ..verifier.recovery import retry_action
from .prompts import FINISH_TOOL, SYSTEM_PROMPT, task_message
from ..environment.evidence import vendor_evidence

DEFAULT_MAX_STEPS = 30


class AgentState(TypedDict, total=False):
    task_id: str
    goal: str
    messages: List[Any]
    step: int                         # agent tool calls executed so far
    max_steps: int
    latest_action: Optional[Dict[str, Any]]      # {"tool", "args", "id", "confidence"}
    pending: Optional[Dict[str, Any]]            # record being built for the current step
    trajectory: List[Dict[str, Any]]             # completed step records (research log)
    done: bool
    done_reason: str                  # finish | gave_up | no_tool_call | max_steps
    final_summary: str
    llm_calls: int
    usage: Dict[str, int]             # agent tokens; episode summary adds verifier tokens
    oracle_pass: bool
    oracle_diff: Dict[str, Any]
    verifier_calls: int
    verifier_usage: Dict[str, int]
    verifier_latency_ms: float
    error: Optional[str]
    error_details: Optional[Dict[str, Any]]
    agent_responses: List[Dict[str, Any]]


def _tool_content(observed: Any) -> str:
    return json.dumps(observed, default=str)


def _add_usage(usage: Dict[str, int], msg: AIMessage) -> Dict[str, int]:
    meta = getattr(msg, "usage_metadata", None) or {}
    out = dict(usage)
    out["input_tokens"] = out.get("input_tokens", 0) + int(meta.get("input_tokens", 0) or 0)
    out["output_tokens"] = out.get("output_tokens", 0) + int(meta.get("output_tokens", 0) or 0)
    return out


def _finish_from_failed_call(exc) -> Optional[tuple]:
    """If the provider rejected a call whose arguments look like finish(status, summary), return them."""
    text = str(exc)
    if "tool_use_failed" not in text:
        return None
    body = getattr(exc, "body", None)
    gen = None
    if isinstance(body, dict):
        gen = (body.get("error") or body).get("failed_generation")
    if gen is None:
        import re
        m = re.search(r"'failed_generation': '(.*)'\s*}\s*}?\s*$", text, re.S)
        gen = m.group(1).encode().decode("unicode_escape") if m else None
    try:
        args = json.loads(gen).get("arguments") or {}
        if isinstance(args, str):
            args = json.loads(args)
    except Exception:  # noqa: BLE001
        return None
    if "summary" in args or "status" in args:
        return str(args.get("status", "done")), str(args.get("summary", ""))
    return None


def build_graph(env: ProcurementEnv, llm, policy: str = "A", controller=None, cache=None,
                verifier_llm=None, policy_config=None):
    """Compile the agent graph for one episode on `env` under verification `policy`."""
    settings = validate_policy_config(policy_config)
    from ..environment.variants import vendor_rule_prompt
    require_vendor_approval = env.task.expected_final_state.get('vendor_approval_required', True)
    if policy not in ("A", "B", "C", "D", "E"):
        raise ValueError(f"Unknown policy: {policy}")
    if policy != "A" and verifier_llm is None:
        raise ValueError("A verifier_llm is required for verification policies")

    def init(state: AgentState) -> AgentState:
        max_steps = state.get("max_steps", DEFAULT_MAX_STEPS)
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        return {
            "task_id": env.task.id,
            "goal": env.task.goal,
            "messages": [SystemMessage(vendor_rule_prompt(SYSTEM_PROMPT, require_vendor_approval)),
                         HumanMessage(task_message(env.task))],
            "step": 0,
            "trajectory": [],
            "done": False,
            "done_reason": "",
            "final_summary": "",
            "llm_calls": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "latest_action": None,
            "pending": None,
            "max_steps": max_steps,
            "verifier_calls": 0,
            "verifier_usage": {"input_tokens": 0, "output_tokens": 0},
            "verifier_latency_ms": 0.0,
            "error": None,
        }

    def agent(state: AgentState) -> AgentState:
        update: AgentState = {"llm_calls": state["llm_calls"], "usage": state["usage"],
                              "agent_responses": list(state.get("agent_responses", []))}
        for attempt in (1, 2):
            update["llm_calls"] += 1
            try:
                evidence = vendor_evidence(state.get('trajectory', []), require_vendor_approval)
                model_messages = state['messages']
                if state.get('trajectory'):
                    model_messages = model_messages + [HumanMessage(
                        'Observed working summary (not ground truth): ' + json.dumps(evidence))]
                ai: AIMessage = llm.invoke(model_messages)
            except Exception as e:  # noqa: BLE001
                finished = _finish_from_failed_call(e)
                if finished is None:
                    return {**update, "done": True, "done_reason": "error",
                            "error": f"{type(e).__name__}: {e}", "error_details": error_details(e)}
                status, summary = finished
                return {**update, "done": True,
                        "done_reason": "gave_up" if status == "gave_up" else "finish",
                        "final_summary": summary, "latest_action": None}
            calls = list(ai.tool_calls or [])
            reason = ai.response_metadata.get("finish_reason")
            usage = _add_usage({}, ai)
            update["usage"] = _add_usage(update["usage"], ai)
            update["agent_responses"].append({"call": update["llm_calls"], "step": state["step"],
                                              "attempt": attempt, "finish_reason": reason,
                                              "tool_call_count": len(calls),
                                              'near_context_limit': ai.response_metadata.get('near_context_limit'),
                                              'context_length': ai.response_metadata.get('context_length'), **usage})
            update['agent_responses'][-1]['public_text'] = ai.content if isinstance(ai.content, str) else ''
            logged_calls = copy.deepcopy(calls)
            for logged in logged_calls:
                if '_confidence' in logged['args']:
                    logged['args']['_confidence'] = parse_confidence(logged['args']['_confidence'])
            update['agent_responses'][-1]['tool_calls'] = logged_calls
            if reason != "length" or calls:
                break
        if reason == "length" and not calls:
            return {**update, "done": True, "done_reason": "truncated",
                    "error": "TruncatedResponse: output limit reached without a tool call"}
        messages = state["messages"] + [ai]
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
        args = dict(first.get("args") or {})
        confidence = parse_confidence(args.pop("_confidence", None))
        action = {"tool": first["name"], "args": args, "id": first["id"], "confidence": confidence}
        return {**update, "messages": messages, "latest_action": action}

    def tool_exec(state: AgentState) -> AgentState:
        a = state["latest_action"]
        record = env.execute(a["tool"], a["args"], origin="agent")
        record.update(action_confidence=a["confidence"],
                      confidence_source="self_reported" if a["confidence"] is not None else "unavailable")
        return {"pending": record}

    def fault_injection(state: AgentState) -> AgentState:
        record = env.apply_fault(state["pending"])
        return {"pending": record}

    def policy_router(state: AgentState) -> AgentState:
        r = dict(state["pending"])
        a = state["latest_action"]
        verify, reason = should_verify(policy=policy,
                                       action={"tool": a["tool"], "args": r["args"],
                                               "confidence": a["confidence"]},
                                       result=r["observed_result"],
                                       history=observation_history(state["trajectory"]),
                                       step=state["step"], controller=controller, cache=cache,
                                       config=settings, vendor_approval_required=require_vendor_approval)
        r.update(verify_decision=bool(verify), trigger_reason=reason,
                 agent_step=state["step"], verifier_verdict=None, recovery_attempts=0,
                 recovery_records=[], final_result_used=r["observed_result"],
                 recovered=False, unrecovered_fault=False, replan_requested=False)
        return {"pending": r}

    def verifier(state: AgentState) -> AgentState:
        r = copy.deepcopy(state["pending"])
        current = r["recovery_records"][-1] if r["recovery_records"] else r
        history = state["trajectory"]
        if r["recovery_records"]:
            history = history + [r]
        check = verify_step(verifier_llm, state["goal"],
                            {"tool": current["tool"], "args": current["args"]},
                            current["observed_result"], history, require_vendor_approval)
        current.update(verifier_verdict=check["verdict"], verifier_error=check["error"],
                       verifier_usage=check["usage"], verifier_latency_ms=check["latency_ms"],
                       observable_checks=check['observable_checks'])
        if check["error_details"]:
            current["verifier_error_details"] = check["error_details"]
        # Recovered means the verifier accepted the retry, not that the oracle passed.
        if r["recovery_attempts"]:
            r["recovered"] = not check["verdict"]["suspicious"]
        usage = dict(state["verifier_usage"])
        for key in usage:
            usage[key] += check["usage"][key]
        return {"pending": r, "verifier_calls": state["verifier_calls"] + 1,
                "verifier_usage": usage,
                "verifier_latency_ms": state["verifier_latency_ms"] + check["latency_ms"]}

    def recovery(state: AgentState) -> AgentState:
        r = copy.deepcopy(state["pending"])
        retry = retry_action(env, r)
        # Automatic retries have no new model-generated action confidence.
        retry.update(action_confidence=None, confidence_source="unavailable")
        r["recovery_records"] = [retry]
        r["recovery_attempts"] = 1
        r["final_result_used"] = retry["observed_result"]
        return {"pending": r}

    def replan(state: AgentState) -> AgentState:
        r = dict(state["pending"])
        current = r["recovery_records"][-1] if r["recovery_records"] else r
        concern = current["verifier_verdict"]["reason"]
        observed = current['observed_result']
        persistent = isinstance(observed, dict) and 'error' in observed and not observed.get('timeout')
        if r.get('invalid_call') or persistent:
            concern += ' Correct the arguments or discover valid IDs using a read; do not repeat the same failing call.'
        elif r["tool"] in HIGH_RISK_TOOLS or r["tool"] in MEDIUM_RISK_TOOLS:
            concern += (" The write may already have succeeded. Check its effects with a read-only "
                        "tool before attempting it again. For purchase orders use check_existing_orders.")
        r.update(replan_requested=True, unrecovered_fault=True, recovery_concern=concern)
        return {"pending": r}

    def observe(state: AgentState) -> AgentState:
        r = dict(state["pending"])
        retries = r.pop("recovery_records")
        a = state["latest_action"]
        # The agent sees the OBSERVED result only — never the true result.
        msg = ToolMessage(content=_tool_content(r["final_result_used"]), tool_call_id=a["id"])
        messages = state["messages"] + [msg]
        if retries or r["replan_requested"]:
            details = {"action": {"tool": r["tool"], "args": r["args"]},
                       "original_observation": r["observed_result"],
                       "latest_observation": r["final_result_used"],
                       "retry_count": r["recovery_attempts"],
                       "concern": r.get("recovery_concern", "")}
            instruction = "Replan using this concern." if r["replan_requested"] else "Review the retry evidence."
            messages.append(HumanMessage(
                content=instruction + " Recovery evidence: " + _tool_content(details)))
        step = state["step"] + 1
        out: AgentState = {"messages": messages, "trajectory": state["trajectory"] + [r] + retries,
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

    def after_policy(state: AgentState) -> str:
        return "verifier" if state["pending"]["verify_decision"] else "observe"

    def after_verifier(state: AgentState) -> str:
        r = state["pending"]
        current = r["recovery_records"][-1] if r["recovery_records"] else r
        if not current["verifier_verdict"]["suspicious"]:
            return "observe"
        # A broken verifier is not evidence that a write should be executed again.
        if current["verifier_error"] or r["recovery_attempts"] >= 1:
            return "replan"
        observed = current['observed_result']
        if r.get('invalid_call') or (isinstance(observed, dict) and 'error' in observed
                                    and not observed.get('timeout')):
            return 'replan'
        if r["tool"] in HIGH_RISK_TOOLS or r["tool"] in MEDIUM_RISK_TOOLS:
            return "replan"
        return "recovery"

    g = StateGraph(AgentState)
    for name, fn in [("init", init), ("agent", agent), ("tool_exec", tool_exec),
                     ("fault_injection", fault_injection), ("policy_router", policy_router),
                     ("verifier", verifier), ("recovery", recovery), ("replan", replan),
                     ("observe", observe), ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "init")
    g.add_edge("init", "agent")
    g.add_conditional_edges("agent", after_agent, {"tool_exec": "tool_exec", "finalize": "finalize"})
    g.add_edge("tool_exec", "fault_injection")
    g.add_edge("fault_injection", "policy_router")
    g.add_conditional_edges("policy_router", after_policy,
                            {"verifier": "verifier", "observe": "observe"})
    g.add_conditional_edges("verifier", after_verifier,
                            {"observe": "observe", "recovery": "recovery", "replan": "replan"})
    g.add_edge("recovery", "verifier")
    g.add_edge("replan", "observe")
    g.add_conditional_edges("observe", after_observe, {"agent": "agent", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile().with_config(recursion_limit=10 * DEFAULT_MAX_STEPS + 20)


def run_episode(task, llm, policy: str = "A", seed: int = 0, fault_rate: float = 0.0,
                max_steps: int = DEFAULT_MAX_STEPS, injector=None, model_name: str = "",
                controller=None, cache=None, verifier_llm=None,
                verifier_model_name: str = "", policy_config=None) -> Dict[str, Any]:
    """
    Run one task end to end and return a summary + full trajectory.
    Policies other than A require an explicit verifier_llm. Steps count agent
    actions; tool_calls and trajectory also include retries. llm_calls counts
    agent invocations; total_llm_calls includes verification. Token usage is
    provider-reported usage, so failed calls may have unknown token cost.
    fault_rate == 0 and no injector → clean environment.
    policy_config sets C's interval and D's confidence threshold. The resolved
    settings are copied into the summary, including when an episode fails.
    """
    from ..faults.injector import FaultInjector
    settings = validate_policy_config(policy_config)
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if injector is None and fault_rate > 0:
        injector = FaultInjector(seed=seed, fault_rate=fault_rate)
    env = ProcurementEnv(task, injector=injector)
    graph = build_graph(env, llm, policy=policy, controller=controller, cache=cache,
                        verifier_llm=verifier_llm, policy_config=settings)

    t0 = time.time()
    error = None
    try:
        # A step can include two verifier visits, one retry, and one replan node.
        last: Dict[str, Any] = {}
        for snapshot in graph.stream({"max_steps": max_steps}, stream_mode="values",
                                     config={"recursion_limit": 10 * max_steps + 20}):
            last = snapshot
        final = last
    except Exception as e:  # noqa: BLE001 — an LLM/API failure must not lose the episode log
        error = f"{type(e).__name__}: {e}"
        passed, diff = oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)
        # Merge partial graph metadata with every executed tool call, including retries.
        logged = {r["step"]: r for r in last.get("trajectory", [])}
        if last.get("pending"):
            pending = dict(last["pending"])
            for retry in pending.pop("recovery_records", []):
                logged[retry["step"]] = retry
            logged[pending["step"]] = pending
        traj = [logged.get(r["step"], r) for r in env.records]
        final = {**last, "trajectory": traj,
                 "step": sum(r["origin"] == "agent" for r in traj), "done_reason": "error",
                 "final_summary": "", "llm_calls": last.get("llm_calls"),
                 "usage": last.get("usage", {}), "oracle_pass": passed, "oracle_diff": diff,
                 "error_details": error_details(e)}

    traj = final["trajectory"]
    agent_usage = final.get("usage", {})
    verifier_usage = final.get("verifier_usage", {})
    usage = {}
    for key in ("input_tokens", "output_tokens"):
        usage[key] = agent_usage.get(key, 0) + verifier_usage.get(key, 0)
    verifier_calls = final.get("verifier_calls", 0)
    return {
        "task_id": task.id, "tier": task.tier, "family": task.family,
        "policy": policy, "seed": seed, "fault_rate": fault_rate, "model": model_name,
        "policy_config": settings, "max_steps": max_steps,
        "vendor_rule": 'qualified' if task.expected_final_state.get('vendor_approval_required', True) else 'suspension_only',
        "oracle_pass": final["oracle_pass"], "oracle_diff": final["oracle_diff"],
        "done_reason": final["done_reason"], "final_summary": final.get("final_summary", ""),
        "steps": final["step"], "tool_calls": len(traj), "llm_calls": final.get("llm_calls"),
        "verifier_calls": verifier_calls,
        "total_llm_calls": (final.get("llm_calls") or 0) + verifier_calls,
        "usage": usage, "agent_usage": agent_usage, "verifier_usage": verifier_usage,
        "verifier_model": verifier_model_name,
        "verifier_latency_ms": round(final.get("verifier_latency_ms", 0.0), 3),
        "recovery_attempts": sum(r.get("recovery_attempts", 0) for r in traj),
        "recovered_steps": sum(bool(r.get("recovered")) for r in traj),
        "unrecovered_steps": sum(bool(r.get("unrecovered_fault")) for r in traj),
        "faults_injected": sum(1 for r in traj if r.get("fault_injected")),
        "verify_triggered": sum(1 for r in traj if r.get("verify_decision") and r["origin"] == "agent"),
        "invalid_calls": sum(1 for r in traj if r.get("invalid_call")),
        "wall_time_s": round(time.time() - t0, 3), "error": error or final.get("error"),
        "error_details": final.get("error_details"),
        "agent_responses": final.get("agent_responses", []),
        "trajectory": traj,
    }
