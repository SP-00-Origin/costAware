"""Keep the original benchmark and suspension-focused alternative distinguishable."""
import pytest

from src.environment.env import ProcurementEnv
from src.environment.evidence import assess_vendor, vendor_evidence
from src.environment.tasks import get_task, load_tasks
from src.environment.variants import vendor_rule_task
from src.evaluation.oracle import oracle_check
from src.evaluation.validate import validate_task
from src.policies.policies import observation_issues


@pytest.mark.parametrize('task', load_tasks(), ids=lambda task: task.id)
def test_suspension_variant_references_and_negatives_are_valid(task):
    original = task.model_dump()
    alternative = vendor_rule_task(task, 'suspension_only')
    assert task.model_dump() == original
    assert validate_task(alternative) == []


@pytest.mark.parametrize('suspended,eligible,passes', [(False, True, True), (True, True, False), (False, False, False)])
def test_alternative_ignores_supplier_approval_but_keeps_suspension_and_eligibility(suspended, eligible, passes):
    task = get_task('T01')
    task.initial_state['vendors'][0].update(approved=False, suspended=suspended, eligible=eligible)
    env = ProcurementEnv(task)
    env.run_actions(task.reference_solution)
    assert not oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)[0]
    alternative = vendor_rule_task(task, 'suspension_only')
    assert oracle_check(env.true_state, alternative.expected_final_state, env.sim.initial_state)[0] is passes


def test_t18_variant_changes_cheapest_legal_vendor_and_negative_not_original_task():
    task = get_task('T18')
    alternative = vendor_rule_task(task, 'suspension_only')
    assert task.expected_final_state['orders'][0]['vendor_id'] == 'V1'
    assert alternative.expected_final_state['orders'][0]['vendor_id'] == 'V2'
    assert alternative.negatives[0]['name'] == 'suspended_replacement'
    assert 'suspended or not approved' not in alternative.goal


def test_variant_summary_and_diagnostics_do_not_require_supplier_approval():
    observed = {'id': 'V2', 'approved': False, 'suspended': False, 'eligible': True}
    assert assess_vendor(observed, require_approval=False)['status'] == 'usable'
    summary = vendor_evidence([{'tool': 'check_vendor_status', 'observed_result': observed}], require_approval=False)
    assert summary['vendors']['V2']['standing'] == 'usable'
    assert 'approved' not in summary['vendors']['V2']
    observed.pop('approved')
    assert observation_issues('check_vendor_status', observed)
    assert not observation_issues('check_vendor_status', observed, require_vendor_approval=False)


def test_variant_does_not_expose_or_inject_faults_into_ignored_approval_metadata():
    task = vendor_rule_task(get_task('T18'), 'suspension_only')
    env = ProcurementEnv(task)
    for tool in ('check_vendor_status', 'get_vendor_details'):
        record = env.call(tool, {'vendor_id': 'V2'})
        assert 'approved' not in record['observed_result']
        assert 'approved' not in record['true_result']
    assert env.true_state.vendors['V2'].approved is False  # Legacy state remains intact.


def test_scripted_variant_records_the_rule_and_transformed_task(tmp_path):
    from experiments.run_experiment import load_config, run_batch
    from src.evaluation.analysis import read_run
    from pathlib import Path
    config = load_config(Path('experiments/configs/phase7_smoke.json'))
    config.update(tasks=['T18'], policies=['A'], seeds=[7], fault_rate=0,
                  vendor_rule='suspension_only')
    path = run_batch(config, tmp_path / 'variant', 'variant-control')
    header, episodes = read_run(path)
    assert header['config']['vendor_rule'] == 'suspension_only'
    snapshot = header['task_snapshots']['T18']
    assert snapshot['expected_final_state']['vendor_approval_required'] is False
    assert episodes[0]['result']['oracle_pass']
    assert episodes[0]['result']['vendor_rule'] == 'suspension_only'


def test_unknown_variant_rejected():
    with pytest.raises(ValueError, match='vendor_rule'):
        vendor_rule_task(get_task('T18'), 'unknown')


def test_variant_rule_is_explicit_in_agent_and_verifier_inputs():
    import json
    from langchain_core.messages import AIMessage
    from src.agent.graph import run_episode
    from src.verifier.verifier import verify_step
    from tests.test_agent import ListModel, FINISH

    class Agent(ListModel):
        def invoke(self, messages):
            assert 'approved=true' not in messages[0].content
            assert 'Supplier approval status is ignored' in messages[0].content
            return super().invoke(messages)

    run_episode(vendor_rule_task(get_task('T01'), 'suspension_only'), Agent([FINISH]))

    class Verifier:
        def invoke(self, messages):
            evidence = json.loads(messages[-1].content)
            assert 'approved=true' not in messages[0].content
            assert 'approved' not in evidence['tool_contract']['required_result_fields']
            assert not evidence['observable_checks']['issues']
            assert evidence['vendor_evidence']['vendors']['V2']['standing'] == 'usable'
            return AIMessage(content='{"suspicious": false, "reason": "Complete nonsuspended eligible status."}')

    result = verify_step(Verifier(), 'Buy from an eligible nonsuspended supplier',
        {'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'}},
        {'id': 'V2', 'suspended': False, 'eligible': True}, [], require_vendor_approval=False)
    assert result['error'] is None


def test_dashboard_labels_variant_separately():
    from src.evaluation.dashboard import render_project_dashboard
    html = render_project_dashboard([{'id': 'variant', 'provider': 'ollama', 'model': 'qwen3:8b',
        'fault_rate': 0.25, 'href': 'run.html', 'summary': {}, 'vendor_rule': 'suspension_only'}], [])
    assert 'suspension_only' in html
