"""Replay a completed Phase 8 baseline and write its evidence and comparisons."""
import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
from pathlib import Path
from random import Random
from statistics import mean, median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.run_experiment import load_config
from src.environment.env import ProcurementEnv
from src.environment.tasks import Task
from src.evaluation.analysis import read_run, write_report
from src.evaluation.oracle import oracle_check
from src.evaluation.trajectory import changes
from src.evaluation.validate import validate_all
from src.faults.replay import replay_records
from src.policies.policies import should_verify


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(', ', ': '))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_episode(ep, task, config):
    steps, result = ep['trajectory'], ep['result']
    label = ep['episode_id']
    mismatches = replay_records(task, steps, ep['seed'], config['fault_rate'])
    require(not mismatches, f'{label} replay mismatch: {mismatches[:1]}')
    env = ProcurementEnv(task)
    history = []
    for step in steps:
        env.call(step['tool'], step['args'], origin=step['origin'])
        if step['origin'] == 'agent' and 'verify_decision' in step:
            action = dict(tool=step['tool'], args=step['args'], confidence=step.get('action_confidence'))
            choice = should_verify(ep['policy'], action, step['observed_result'], history,
                                   step['agent_step'], config=config['policy_config'])
            require(choice == (step['verify_decision'], step['trigger_reason']), f'{label} router mismatch')
        elif step['origin'] == 'recovery':
            original = history[-1]
            require(original['origin'] == 'agent' and original.get('verify_decision')
                    and original['risk'] == 'low' and original.get('recovery_attempts') == 1
                    and original['tool'] == step['tool'] and original['args'] == step['args']
                    and original['step'] == step.get('recovery_of'), f'{label} unexpected retry')
        if ep['status'] == 'completed':
            require(bool(step['verify_decision']) == bool(step.get('verifier_verdict')),
                    f'{label} selected call and verdict count disagree')
        history.append(step)
    passed, diff = oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)
    if 'oracle_pass' in result:
        require((passed, diff) == (result['oracle_pass'], result['oracle_diff']), f'{label} oracle mismatch')
    else:
        require(ep['status'] == 'error', f'{label} has no oracle result')
    agent = [s for s in steps if s['origin'] == 'agent']
    selected = [s for s in agent if s.get('verify_decision')]
    checks = [s for s in steps if s.get('verifier_verdict') is not None]
    verdicts = Counter((bool(s['fault_injected']), s['verifier_verdict']['suspicious'])
                       for s in checks if not s.get('verifier_error'))
    faults = [s for s in steps if s.get('fault_injected')]
    retries = len(steps) - len(agent)
    counts = dict(steps=len(agent), verify_triggered=len(selected), verifier_calls=len(checks),
                  faults_injected=len(faults), recovery_attempts=retries, tool_calls=len(steps))
    for key, actual in counts.items():
        if key in result:
            require(actual == result[key], f'{label} {key} mismatch')
    vu = result.get('verifier_usage', {})
    au = result.get('agent_usage', {})
    for key in ('input_tokens', 'output_tokens'):
        require(sum((msg.get(key) or 0) for msg in result.get('agent_responses', [])) == au.get(key, 0),
                f'{label} agent {key} mismatch')
        require(sum(s.get('verifier_usage', {}).get(key, 0) for s in checks) == vu.get(key, 0),
                f'{label} verifier {key} mismatch')
        require(result.get('usage', {}).get(key, 0) == au.get(key, 0) + vu.get(key, 0),
                f'{label} combined {key} mismatch')
    responses = result.get('agent_responses', [])
    failed = {k: v for k, v in result.get('oracle_diff', {}).items() if not v['pass']}
    return dict(episode=label, task=ep['task_id'], seed=ep['seed'], policy=ep['policy'], tier=task.tier,
                outcome='ERROR' if ep['status'] == 'error' else ('PASS' if passed else 'FAIL'),
                stop=result.get('done_reason', 'error'), oracle_failures=failed,
                error=result.get('error'), agent_calls=result.get('llm_calls') or 0, recorded_agent_responses=len(responses),
                agent_actions=len(agent), selected=len(selected), calls=len(checks), faults=len(faults),
                exposed=sum(bool(s['fault_injected']) for s in agent),
                caught=sum(bool(s['fault_injected']) for s in selected),
                tp=verdicts[True, True], fn=verdicts[True, False], fp=verdicts[False, True], tn=verdicts[False, False],
                retries=retries, accepted_retries=result.get('recovered_steps', 0),
                replans=sum(bool(s.get('replan_requested')) for s in agent),
                agent_tokens=sum(au.values()), verifier_tokens=sum(vu.values()), tokens=sum(au.values()) + sum(vu.values()),
                seconds=result.get('wall_time_s', 0), verifier_seconds=result.get('verifier_latency_ms', 0) / 1000,
                verifier_errors=sum(bool(s.get('verifier_error')) for s in checks),
                context_warnings=sum(bool(r.get('near_context_limit')) for r in responses),
                peak_input=max((r.get('input_tokens') or 0 for r in responses), default=0),
                diagnostic_disagreements=sum(bool(s.get('observable_checks', {}).get('llm_accepted_despite_failed_check')) for s in checks),
                invalid_calls=sum(bool(s.get('invalid_call')) for s in steps),
                trigger_reasons=dict(Counter(s['trigger_reason'] for s in selected)))


def fractions(rows):
    def total(key):
        return sum(r[key] for r in rows)
    exposed = [r for r in rows if r['faults'] and r['outcome'] != 'ERROR']
    return dict(success=(sum(r['outcome'] == 'PASS' for r in rows), len(rows)),
                calls=(total('calls'), len(rows)), tokens=(total('tokens'), len(rows)),
                seconds=(total('seconds'), len(rows)), selection=(total('selected'), total('agent_actions')),
                checks_per_action=(total('calls'), total('agent_actions')),
                trigger_precision=(total('caught'), total('selected')), trigger_recall=(total('caught'), total('exposed')),
                tpr=(total('tp'), total('tp') + total('fn')), fnr=(total('fn'), total('tp') + total('fn')),
                fpr=(total('fp'), total('fp') + total('tn')),
                episode_errors=(sum(r['outcome']=='ERROR' for r in rows),len(rows)),
                verifier_errors=(total('verifier_errors'), total('calls')),
                retries=(total('retries'), len(rows)), retry_accept=(total('accepted_retries'), total('retries')),
                fault_pass=(sum(r['outcome'] == 'PASS' for r in exposed), len(exposed)),
                fault_fail=(sum(r['outcome'] == 'FAIL' for r in exposed), len(exposed)))


def ratio(pair):
    return pair[0] / pair[1] if pair[1] else None


def interval(samples):
    valid = sorted(x for x in samples if x is not None)
    if not valid:
        return None
    return [valid[max(0, round(len(valid) * q) - 1)] for q in (.025, .975)]


def explain_check(name, check):
    expected, actual = check['expected'], check['actual']
    if name.startswith('order[') and isinstance(actual, dict):
        if 'matching_active_orders' in actual:
            matches = actual['matching_active_orders']
            return f"{name} required one active order and found {len(matches)}."
        differences = [f"{key} was {actual[key]} (required {value})" for key, value in expected.items()
                       if key in actual and actual[key] != value]
        if differences:
            return f"{name} on {actual.get('po_id', 'the matched order')}: " + ', '.join(differences) + '.'
    if name == 'vendor_standing':
        return f"Active order(s) {', '.join(actual)} used a supplier that failed the standing rule."
    if name == 'valid_quotes':
        return f"The quote-validity check identified {compact(actual)}."
    return f"{name} required {compact(expected)} and ended at {compact(actual)}."


def failure_types(row):
    labels = set()
    for name, check in row['oracle_failures'].items():
        expected, actual = check['expected'], check['actual']
        if not name.startswith('order[') or not isinstance(actual, dict):
            labels.add(name.split(':')[0])
            continue
        if 'matching_active_orders' in actual:
            labels.add('extra matching orders' if actual['matching_active_orders'] else 'missing active order')
            continue
        for field in ('vendor_id', 'quantity', 'status', 'unit_price', 'approval_valid'):
            if field in expected and field in actual and expected[field] != actual[field]:
                labels.add('order ' + field)
        if 'vendor_in' in expected and actual.get('vendor_id') not in expected['vendor_in']:
            labels.add('order vendor_id')
        if 'max_unit_price' in expected and actual['unit_price'] > expected['max_unit_price'] + .01:
            labels.add('order price ceiling')
    return sorted(labels)


def statistics(rows, tasks):
    rng = Random(0)
    draws = [rng.choices(range(len(tasks)), k=len(tasks)) for _ in range(2000)]
    summaries, paired, reference = {}, {}, {}
    for policy in 'BACD':
        group = [r for r in rows if r['policy'] == policy]
        by_task = [fractions([r for r in group if r['task'] == t]) for t in tasks]
        metrics = {}
        for key, pair in fractions(group).items():
            nums, dens = zip(*(x[key] for x in by_task))
            samples = [ratio((sum(nums[i] for i in draw), sum(dens[i] for i in draw))) for draw in draws]
            metrics[key] = dict(estimate=ratio(pair), ci95=interval(samples), numerator=pair[0], denominator=pair[1])
            if policy == 'B':
                reference[key] = samples
            elif key in ('success', 'calls', 'tokens', 'seconds'):
                differences = [a-b for a, b in zip(samples, reference[key]) if a is not None and b is not None]
                paired.setdefault(policy, {})[key] = dict(
                    delta=ratio(pair) - summaries['B'][key]['estimate'], ci95=interval(differences))
        summaries[policy] = metrics
    return summaries, paired


def frontiers(summary):
    front = {}
    for cost in ('calls', 'tokens', 'seconds'):
        candidates = {p: (s[cost]['estimate'], s['success']['estimate']) for p, s in summary.items()}
        front[cost] = []
        for p, (c, success) in sorted(candidates.items(), key=lambda x: x[1][0]):
            dominators = [q for q, (other_c, other_s) in candidates.items()
                          if other_c <= c and other_s >= success and (other_c < c or other_s > success)]
            best = max(s for k, s in candidates.values() if k <= c)
            front[cost].append(dict(policy=p, cost=c, success=success, dominated_by=dominators,
                                    best_at_budget=best))
    return front


def write_short_report(path, data):
    text = ['# Phase 8 local Qwen baseline', '', f"Run {data['run_id']}.",
            'Twenty synthetic procurement tasks, policies A–D, fault seeds 7, 12 and 23. Each policy ran 60 episodes.',
            '', '| Policy | Pass / 60 | Success (95% task-cluster interval) | Selected actions | Verifier calls | Tokens | Mean wall seconds |',
            '|---|---:|---|---:|---:|---:|---:|']
    for p in 'ABCD':
        s = data['diagnostics'][p]
        m = data['metrics'][p]
        lo, hi = m['success']['ci95']
        text.append(f"| {p} | {s['passed']}/60 | {s['success_rate']:.1%} ({lo:.1%} to {hi:.1%}) | "
                    f"{s['verify_triggered']} | {s['verifier_calls']} | {m['tokens']['numerator']:,} | {m['seconds']['estimate']:.1f} |")
    text += ['', '## Paired differences from B', '',
             'Each difference uses the same task and fault seed. Intervals resample 20 whole tasks with replacement 2,000 times.', '']
    for p in 'ACD':
        diff = data['paired'][p]['success']
        lo, hi = diff['ci95']
        text.append(f"- {p} minus B was {100*diff['delta']:+.1f} percentage points (95% interval {lo*100:.1f} to {hi*100:.1f}).")
    text += ['', '## Observed frontiers', '',
             'Efficient policies maximize success at a given mean per-episode cost. A cheaper or equally costly policy with at least as much success dominates when one inequality is strict.', '']
    for cost, entries in data['frontiers'].items():
        text.append(f"- {cost}: " + ', '.join(x['policy'] for x in entries if not x['dominated_by']) + ' on the frontier.')
    text += ['', 'API charges were zero for these local calls. Electricity and ownership cost were unmeasured. '
             'The mean-budget envelope in audit.json is descriptive. It does not simulate imposing a hard limit during an episode.',
             '', '## Audit and artifacts', '',
             f"Replayed {data['replayed_steps']:,} tool events. Checked all 240 planned task–seed–policy combinations, "
             f"20 reference solutions, 20 empty controls and {data['negative_controls']} negative controls. "
             'Verified the final-state oracle, policy routing and workload counters against the log.',
             '', 'The dashboard plots success against verifier calls per action. The episode index records every terminal outcome. '
             'The chronological review lists every fault, selection, verdict, subsequent action and failed oracle requirement. '
             'Faults followed by failures are associations. An agent can miss a requirement despite an accurate reread or finish correctly after a corrupted receipt.',
             '', 'With the frozen generation sources, rebuild the audit from the repository root.', '',
             '```powershell', f'python experiments/audit_phase8.py output/experiments/{data["run_id"]}/events.jsonl', '```']
    path.write_text('\n'.join(text) + '\n', encoding='utf8')


def episode_ledger(ep, row):
    lines = [f"## {row['episode']}  {row['task']}  policy {row['policy']}  seed {row['seed']}  {row['outcome']}",
             '', ep.get('goal', ''), '', f"Agent stopped with `{row['stop']}`. {ep['result'].get('final_summary', '')}", '']
    if ep['result'].get('error'):
        lines.append(f"Runtime error: {ep['result']['error']}")
    for name, check in row['oracle_failures'].items():
        lines.append('- ' + explain_check(name, check))
        lines.append(f"  Expected `{compact(check['expected'])}`, actual `{compact(check['actual'])}`.")
    if row['outcome'] == 'PASS':
        lines.append('All final-state requirements passed.')
    lines.extend(['', 'Tool events in execution order', ''])
    for index, s in enumerate(ep['trajectory']):
        verdict = s.get('verifier_verdict')
        route = s.get('trigger_reason') if s['origin'] == 'agent' else 'retry recheck'
        decision = 'unchecked' if not verdict else ('warned' if verdict['suspicious'] else 'accepted')
        lines.append(f"- Step {s['step']} ({s['origin']}) `{s['tool']} {compact(s['args'])}`. "
                     f"Fault {s.get('fault_injected') or 'none'}. Route {route}. Verifier {decision}.")
        if s.get('fault_injected'):
            lines.append('  Offline observation difference: ' + ' | '.join(changes(s['true_result'], s['observed_result'])))
        if verdict:
            lines.append(f"  Recorded verdict reason: {verdict.get('reason', '')}")
        if s.get('replan_requested'):
            lines.append('  The agent was asked to replan.')
        if s['origin'] == 'agent' and (s.get('fault_injected') or s.get('replan_requested') or s.get('recovery_attempts')):
            if 'final_result_used' in s:
                lines.append(f"  Tool evidence returned to the agent: `{compact(s['final_result_used'])}`.")
            follow = next((later for later in ep['trajectory'][index + 1:] if later['origin'] == 'agent'), None)
            if follow:
                lines.append(f"  Next executed agent action: `{follow['tool']} {compact(follow['args'])}`.")
            else:
                lines.append(f"  The episode ended with `{row['stop']}` after this action.")
    return '\n'.join(lines)


def main(path):
    header, episodes = read_run(path)
    config = load_config(ROOT / 'experiments/configs/phase8_ollama_baseline.json')
    require(config == header['config'], 'Configuration differs from the primary baseline')
    tasks = config['tasks']
    expected = set(itertools.product(tasks, config['seeds'], config['policies']))
    actual = [(e['task_id'], e['seed'], e['policy']) for e in episodes]
    require(set(actual) == expected and len(actual) == len(expected) == 240, 'Unmatched grid')
    require(all(e['status'] in ('completed', 'error') for e in episodes), 'Unfinished grid')
    with path.open(encoding='utf8') as log:
        require(json.loads(next(reversed(log.readlines())))['event'] == 'run_finished', 'Missing run_finished')
    freeze = json.loads(path.with_name('freeze.json').read_text())
    require(freeze['run_id'] == header['run_id'] and freeze['runtime'] == header['runtime'],
            'Run header differs from freeze manifest')
    require(header['runtime']['agent_model']['digest'] == header['runtime']['verifier_model']['digest'],
            'Agent and verifier checkpoint identities disagree')
    archive = path.with_name('baseline_source.zip')
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == freeze['source_archive_sha256'],
            'Source archive differs from freeze manifest')
    for name, digest in freeze['file_sha256'].items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, f'Frozen source differs: {name}')
    snapshots = {k: Task.model_validate(v) for k, v in header['task_snapshots'].items()}
    dataset = [Task.model_validate_json(line) for line in (ROOT / 'tasks/tasks.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    require({t.id:t for t in dataset} == snapshots, 'Logged tasks differ from qualified baseline data')
    controls = validate_all(list(snapshots.values()))
    require(not any(controls.values()), f'Invalid reference or negative control: {controls}')
    rows = [audit_episode(e, snapshots[e['task_id']], config) for e in episodes]
    for row in rows:
        row['failed_conditions'] = failure_types(row)
    summary = write_report(path)
    metrics, paired = statistics(rows, tasks)
    for policy, recorded in summary.items():
        for metric, runner_name in [('success','success_rate'), ('selection','selection_rate'),
                                    ('checks_per_action','verifier_calls_per_action'), ('fault_fail','error_propagation_rate')]:
            require(metrics[policy][metric]['estimate'] == recorded[runner_name],
                    f'{policy} {metric} disagrees with dashboard')
        for metric, runner_name in [('fnr','verifier_false_negative_rate'), ('fpr','verifier_false_positive_rate'),
                                    ('tpr','verifier_true_positive_rate'), ('trigger_recall','trigger_recall'),
                                    ('trigger_precision','trigger_precision')]:
            require(metrics[policy][metric]['estimate'] == recorded['diagnostics'][runner_name],
                    f'{policy} {metric} disagrees with dashboard diagnostics')
    fault_types = {}
    for e in episodes:
        for s in e['trajectory']:
            fault = s.get('fault_injected')
            if fault:
                counts = fault_types.setdefault(fault, Counter())
                counts['events'] += 1
                verdict = s.get('verifier_verdict')
                status = 'error' if s.get('verifier_error') else 'unchecked' if not verdict else 'warned' if verdict['suspicious'] else 'accepted'
                counts[status] += 1
    data = dict(run_id=header['run_id'], replayed_steps=sum(r['agent_actions'] + r['retries'] for r in rows),
                negative_controls=sum(len(t.negatives) for t in snapshots.values()), metrics=metrics, paired=paired,
                frontiers=frontiers(metrics), diagnostics=summary, fault_types=fault_types,
                failure_counts=dict(Counter(label for row in rows if row['outcome']=='FAIL' for label in row['failed_conditions'])),
                episodes=rows)
    highest = max(item['success']['estimate'] for item in metrics.values())
    data['monetary_cost'] = dict(scope='Local inference. No metered provider charge. Total machine cost unmeasured.',
        api_fee_per_episode={p: 0 for p in metrics},
        api_fee_frontier=[p for p in metrics if metrics[p]['success']['estimate'] == highest],
        total_cost_per_episode=None)
    failed_blocks = {(r['task'],r['seed']) for r in rows if r['outcome']=='ERROR'}
    data['latency_sensitivity'] = {}
    for p in 'ABCD':
        group = [r for r in rows if r['policy']==p]
        kept = [r for r in group if (r['task'],r['seed']) not in failed_blocks]
        data['latency_sensitivity'][p] = dict(all_median_seconds=median(r['seconds'] for r in group),
            kept_pairs=len(kept), complete_blocks_mean_seconds=mean(r['seconds'] for r in kept) if kept else None,
            complete_blocks_passed=sum(r['outcome']=='PASS' for r in kept))
    path.with_name('audit.json').write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf8')
    export_rows = [{**r, 'oracle_failures': compact(r['oracle_failures']), 'trigger_reasons': compact(r['trigger_reasons'])} for r in rows]
    write_csv(path.with_name('episode_index.csv'), export_rows)
    ledger = [episode_ledger(e, r) for e, r in zip(episodes, rows)]
    path.with_name('episode_review.md').write_text('# Phase 8 episode evidence\n\n' + '\n\n'.join(ledger), encoding='utf8')
    write_short_report(path.with_name('phase8_report.md'), data)
    print(f"Audited {len(rows)} episodes, {data['replayed_steps']} tool events and {len(tasks)} reference controls.")
    for p in 'ABCD':
        print(p, summary[p]['passed'], '/', summary[p]['planned'], 'calls', summary[p]['verifier_calls'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    main(parser.parse_args().log)
