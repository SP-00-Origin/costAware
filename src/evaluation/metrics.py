"""Policy and verifier metrics derived from reconstructed episodes."""

from collections import Counter


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def verification_diagnostics(steps):
    """Use injected faults as offline labels and keep selection and verdicts separate."""
    actions = [step for step in steps if step.get("origin") == "agent"
               and type(step.get("verify_decision")) is bool]
    selected = [step for step in actions if step["verify_decision"]]
    faulted = sum(bool(step.get("fault_injected")) for step in actions)
    faulted_selected = sum(bool(step.get("fault_injected")) for step in selected)
    triggers = Counter(step.get("trigger_reason") or "unknown" for step in selected)
    verdicts = Counter()
    for step in steps:
        verdict = step.get("verifier_verdict")
        if not verdict or step.get("verifier_error"):
            continue
        verdicts[bool(step.get("fault_injected")), verdict["suspicious"]] += 1
    tp, fn = verdicts[True, True], verdicts[True, False]
    fp, tn = verdicts[False, True], verdicts[False, False]
    return {
        "selected_actions": len(selected), "faulted_actions": faulted,
        "selected_faulted_actions": faulted_selected, "triggers": dict(triggers),
        "trigger_precision": ratio(faulted_selected, len(selected)),
        "trigger_recall": ratio(faulted_selected, faulted),
        "verdict_counts": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "verifier_true_positive_rate": ratio(tp, tp + fn),
        "verifier_false_negative_rate": ratio(fn, tp + fn),
        "verifier_false_positive_rate": ratio(fp, fp + tn),
        'corrupted_checks': tp + fn,
        'uncorrupted_checks': fp + tn,
        'uncorrupted_tool_error_warnings': sum(
            not step.get('fault_injected') and isinstance(step.get('true_result'), dict)
            and 'error' in step['true_result'] and bool((step.get('verifier_verdict') or {}).get('suspicious'))
            and not step.get('verifier_error') for step in steps),
        'underlying_tool_errors': sum(isinstance(step.get('true_result'), dict)
                                     and 'error' in step['true_result'] for step in steps),
        'invalid_argument_calls': sum(bool(step.get('invalid_call')) for step in steps),
    }


def summarize(episodes):
    groups = {}
    for episode in episodes:
        groups.setdefault(episode["policy"], []).append(episode)
    summary = {}
    for policy, group in groups.items():
        completed = [episode for episode in group if episode["status"] == "completed"]
        faulted = [episode for episode in completed if episode["result"]["faults_injected"]]
        fault_pass = sum(episode["result"]["oracle_pass"] for episode in faulted)
        passed = sum(episode["result"]["oracle_pass"] for episode in completed)
        totals = {}
        recorded = [episode["result"] for episode in group if "steps" in episode["result"]]
        for key in ("steps", "verify_triggered", "verifier_calls", "recovery_attempts",
                    "verifier_latency_ms", "wall_time_s"):
            totals[key] = sum(result[key] for result in recorded)
        for key in ("agent_usage", "verifier_usage"):
            totals[key] = {
                token: sum(result[key].get(token, 0) for result in recorded)
                for token in ("input_tokens", "output_tokens")
            }
        steps = [step for episode in group for step in episode["trajectory"]]
        verifier_errors = sum(bool(step.get("verifier_error")) for step in steps)
        summary[policy] = {
            "planned": len(group), "completed": len(completed), "passed": passed,
            "errors": sum(episode["status"] == "error" for episode in group),
            "incomplete": sum(episode["status"] in ("planned", "interrupted") for episode in group),
            "completion_rate": ratio(len(completed), len(group)),
            "success_rate": ratio(passed, len(group)),
            "faulted_completed": len(faulted),
            "fault_recovery_rate": ratio(fault_pass, len(faulted)),
            "error_propagation_rate": ratio(len(faulted) - fault_pass, len(faulted)),
            "selection_rate": ratio(totals["verify_triggered"], totals["steps"]),
            "verifier_calls_per_action": ratio(totals["verifier_calls"], totals["steps"]),
            "recovery_calls_per_action": ratio(totals["recovery_attempts"], totals["steps"]),
            "verifier_errors": verifier_errors,
            "verifier_error_rate": ratio(verifier_errors, totals["verifier_calls"]),
            "diagnostics": verification_diagnostics(steps),
            'agent_claimed_done': sum(e['result'].get('done_reason') == 'finish' for e in group),
            'agent_gave_up': sum(e['result'].get('done_reason') == 'gave_up' for e in group),
            'near_context_calls': sum(bool(r.get('near_context_limit')) for e in group
                                      for r in e['result'].get('agent_responses', [])),
            **totals,
        }
    return summary
