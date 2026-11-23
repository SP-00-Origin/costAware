"""Readable episode reports from recorded facts, with no model calls."""
import json
from html import escape


def changes(actual, observed, path='result'):
    """Describe changed fields for offline inspection only."""
    if isinstance(actual, dict) and isinstance(observed, dict):
        lines = []
        for key in sorted(actual.keys() | observed.keys()):
            if key not in observed:
                lines.append(f'{path}.{key}: missing (true value {json.dumps(actual[key])})')
            elif key not in actual:
                lines.append(f'{path}.{key}: added {json.dumps(observed[key])}')
            else:
                lines.extend(changes(actual[key], observed[key], f'{path}.{key}'))
        return lines
    if isinstance(actual, list) and isinstance(observed, list) and len(actual) == len(observed):
        lines = []
        for i, (left, right) in enumerate(zip(actual, observed)):
            lines.extend(changes(left, right, f'{path}[{i}]'))
        return lines
    if actual != observed:
        return [f'{path}: true {json.dumps(actual)}; observed {json.dumps(observed)}']
    return []


def episode_story(episode):
    result = episode['result']
    rows = []
    trajectory = episode['trajectory']
    for index, step in enumerate(trajectory):
        selected = step.get('verify_decision')
        decision = 'Selected' if selected else 'Skipped' if selected is False else 'Not recorded'
        reasons = {'no_verify': 'Policy A uses no separate verifier; agent reads are still allowed', 'always_verify': 'Policy B checks every action',
                   'fixed_schedule': 'Scheduled action under Policy C', 'schema_fail': 'Observed schema or sanity check failed',
                   'high_risk_tool': 'High-risk action', 'low_confidence': 'Agent confidence below threshold',
                   'no_trigger': 'No policy trigger matched', 'recovery_recheck': 'Check the retry observation'}
        reason = step.get('trigger_reason') or 'not recorded'
        verdict = step.get('verifier_verdict')
        check = 'No verifier call recorded.'
        if verdict:
            check = ('Suspicious: ' if verdict['suspicious'] else 'Accepted: ') + verdict['reason']
        if step.get('verifier_error'):
            check = 'Verifier error: ' + step['verifier_error']
        diagnostics = step.get('observable_checks', {})
        if diagnostics.get('issues'):
            check += '\nDeterministic observation checks: ' + '; '.join(diagnostics['issues'])
        if diagnostics.get('llm_accepted_despite_failed_check'):
            check += '\nDisagreement: LLM accepted despite a failed deterministic check.'
        reaction = []
        if step.get('recovery_attempts'):
            reaction.append('Automatic read retry requested.')
        if step.get('replan_requested'):
            reaction.append('Agent was asked to replan: ' + step.get('recovery_concern', ''))
        next_action = next((s for s in trajectory[index + 1:] if s['origin'] == 'agent'), None)
        if next_action:
            reaction.append(f'Next recorded agent action: {next_action["tool"]} '
                            + json.dumps(next_action['args'], sort_keys=True))
        else:
            reaction.append('No later procurement action recorded. Stop: ' + result.get('done_reason', episode['status']))
        fault = step.get('fault_injected')
        corruption = 'No injected corruption recorded.'
        if fault:
            corruption = fault + ': ' + '; '.join(changes(step.get('true_result'), step.get('observed_result')))
        cells = [str(step['step'] + 1) + ' / ' + step['origin'],
                 step['tool'] + '\n' + json.dumps(step['args'], sort_keys=True)
                 + '\nAgent confidence: ' + str(step.get('action_confidence', 'not recorded')),
                 json.dumps(step.get('observed_result'), indent=2, ensure_ascii=False),
                 decision + ': ' + reasons.get(reason, reason) + ' (' + reason + ')',
                 check, ' '.join(reaction), corruption]
        rows.append('<tr>' + ''.join('<td>' + escape(cell) + '</td>' for cell in cells) + '</tr>')
    failed = [name for name, check in result.get('oracle_diff', {}).items() if not check['pass']]
    outcome = ('PASS' if result['oracle_pass'] else 'FAIL') if 'oracle_pass' in result else 'Not available'
    summary = ('Oracle ' + outcome + '; agent stop: ' + result.get('done_reason', episode['status'])
               + '; failed checks: ' + (', '.join(failed) or 'none recorded'))
    claim = result.get('final_summary') or 'No final explanation recorded.'
    return ('<p><strong>' + escape(summary) + '</strong></p><p>Goal: '
            + escape(episode.get('goal', 'Not recorded')) + '</p><p>Agent final statement: '
            + escape(claim) + '</p><p>This timeline shows recorded actions and verifier reasons, '
            'not private agent reasoning. Fault labels and true-value differences below are offline audit data.</p>'
            '<div class="scroll"><table class="timeline"><thead><tr>'
            '<th>Call / origin</th><th>Action and arguments</th><th>Observed result</th>'
            '<th>Verification selection</th><th>Verifier response</th><th>Recorded follow-up</th>'
            '<th>Offline fault audit</th></tr></thead><tbody>' + ''.join(rows)
            + '</tbody></table></div>')
