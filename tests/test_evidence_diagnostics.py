"""Observed evidence, readable diagnostics and controlled fault consequences."""
import json

import pytest
from langchain_core.messages import AIMessage

from src.agent.graph import run_episode
from src.environment.evidence import vendor_evidence
from src.environment.tasks import get_task
from src.evaluation.trajectory import episode_story
from src.faults.replay import ReplayInjector
from src.policies.policies import observation_issues
from src.verifier.verifier import ScriptedVerifier, verify_step


def test_order_summary_tracks_cancellation_replacement_and_approval_separately():
    records = [
        {'tool': 'check_existing_orders', 'observed_result': {'orders': [
            {'id': 'OLD', 'vendor_id': 'BAD', 'status': 'DRAFT', 'quantity': 25}]}},
        {'tool': 'cancel_order', 'observed_result': {'po_id': 'OLD', 'status': 'CANCELLED'}},
        {'tool': 'create_purchase_order', 'observed_result': {'po_id': 'NEW', 'vendor_id': 'GOOD',
            'status': 'DRAFT', 'quantity': 25, 'requires_approval': True}},
        {'tool': 'request_approval', 'observed_result': {'po_id': 'NEW', 'approval_id': 'APR', 'status': 'PENDING'}},
    ]
    summary = vendor_evidence(records)
    assert summary['orders']['OLD']['status'] == 'CANCELLED'
    assert summary['orders']['NEW']['status'] == 'PENDING_APPROVAL'
    assert summary['orders']['NEW']['vendor_id'] == 'GOOD'
    records.extend([
        {'tool': 'approve_order', 'observed_result': {'po_id': 'NEW', 'status': 'APPROVED'}},
        {'tool': 'release_order', 'observed_result': {'po_id': 'NEW', 'status': 'RELEASED'}},
    ])
    assert vendor_evidence(records)['orders']['NEW']['status'] == 'RELEASED'


@pytest.mark.parametrize('failed_result', [
    {'error': 'TIMEOUT', 'timeout': True}, {'parse_error': True},
    {'approved': True, 'suspended': False, 'eligible': True},
])
def test_failed_status_read_does_not_leave_summary_claiming_current_usable_standing(failed_result):
    records = [
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V1', 'approved': True,
            'suspended': False, 'eligible': True}},
        {'tool': 'check_vendor_status', 'args': {'vendor_id': 'V1'}, 'observed_result': failed_result},
    ]
    vendor = vendor_evidence(records)['vendors']['V1']
    assert vendor['standing'] == 'unknown'
    assert vendor['next_read'] == 'check_vendor_status(vendor_id="V1")'


def test_ranked_quote_links_do_not_fabricate_vendor_standing():
    summary = vendor_evidence([{'tool': 'compare_quotes', 'observed_result': {
        'ranked_quotes': [{'id': 'Q1', 'vendor_id': 'V1', 'expired': False}]}}])
    assert summary['quotes']['Q1']['vendor_id'] == 'V1'
    assert summary['vendors']['V1']['standing'] == 'unknown'


def test_specific_diagnostics_are_distinct_from_llm_acceptance_and_visible_in_report():
    observation = {'component_id': 'C-A', 'quotes': [{'id': 'Q1', 'vendor_id': 'V1',
        'unit_price': 480.0, 'quantity': 20, 'shipping_cost': 200.0,
        'total_price': 12720.2, 'status': 'ACTIVE', 'expired': False}]}
    result = verify_step(ScriptedVerifier(), 'Buy ten', {'tool': 'get_quotes', 'args': {}}, observation, [])
    assert not result['verdict']['suspicious']  # The diagnostic must not replace the LLM verdict.
    checks = result['observable_checks']
    assert checks['llm_accepted_despite_failed_check']
    assert '12720.2' in checks['issues'][0] and '9800.0' in checks['issues'][0]
    episode = {'status': 'completed', 'result': {}, 'trajectory': [
        {'step': 0, 'origin': 'agent', 'tool': 'get_quotes', 'args': {},
         'observed_result': observation, 'verifier_verdict': result['verdict'], 'observable_checks': checks}]}
    assert 'LLM accepted despite a failed deterministic check' in episode_story(episode)


def test_missing_fields_and_quantity_errors_have_specific_reasons():
    assert 'result.approved: missing required field' in observation_issues(
        'check_vendor_status', {'id': 'V1', 'suspended': False, 'eligible': True})
    assert not observation_issues('check_vendor_status',
        {'id': 'V2', 'approved': False, 'suspended': True, 'eligible': True})
    issues = observation_issues('modify_order', {'po_id': 'P', 'quantity': 0, 'status': 'DRAFT',
        'total': 100, 'approval_invalidated': False, 'requires_approval': False})
    assert 'result.quantity: quantity must be at least 1' in issues


class ObservedChoiceAgent:
    """Test stand-in: choose V2 if the observed approval permits it, otherwise V1."""
    def __init__(self, recheck):
        self.actions = list(get_task('T18').reference_solution[:4])
        self.actions.append({'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'}})
        self.recheck = recheck
        self.rechecked = False
        self.planned = False
        self.calls = 0

    def invoke(self, messages):
        if not self.actions and not self.planned:
            if self.recheck and not self.rechecked:
                self.actions.append({'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'}})
                self.rechecked = True
            else:
                # Read the actual tool observation, never simulator truth or fault labels.
                status = json.loads(next(m.content for m in reversed(messages) if m.type == 'tool'))
                usable = status.get('approved') is True and status.get('suspended') is False and status.get('eligible') is True
                quote = 'QY2' if usable else 'QY1'
                if not usable:
                    self.actions.append({'tool': 'check_vendor_status', 'args': {'vendor_id': 'V1'}})
                self.actions.extend([
                    {'tool': 'create_purchase_order', 'args': {'project_id': 'PROJ-R', 'quote_id': quote, 'quantity': 25}},
                    {'tool': 'request_approval', 'args': {'po_id': 'PO-0001', 'requester': 'rosa'}},
                    {'tool': 'approve_order', 'args': {'approval_id': 'APR-0001'}},
                    {'tool': 'release_order', 'args': {'po_id': 'PO-0001'}},
                    {'tool': 'finish', 'args': {'status': 'done', 'summary': 'Controlled observation-based choice.'}},
                ])
                self.planned = True
        action = self.actions.pop(0)
        self.calls += 1
        return AIMessage(content='', tool_calls=[{'name': action['tool'], 'args': action['args'], 'id': str(self.calls)}])


@pytest.mark.parametrize('policy', list('ABCD'))
@pytest.mark.parametrize('recheck', [False, True])
def test_decision_critical_false_approval_can_cause_failure_and_recheck_can_correct_it(policy, recheck):
    injector = ReplayInjector([{'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'},
        'observed_result': {'id': 'V2', 'approved': True, 'suspended': False, 'eligible': True},
        'fault_injected': 'contradictory'}])
    result = run_episode(get_task('T18'), ObservedChoiceAgent(recheck), policy=policy,
                         injector=injector, verifier_llm=ScriptedVerifier(), max_steps=20)
    assert result['faults_injected'] == 1
    assert result['oracle_pass'] is recheck
    if not recheck:
        assert not result['oracle_diff']['vendor_standing']['pass']


def test_wrong_write_response_does_not_undo_the_real_correct_order():
    from tests.test_agent import ListModel, call, FINISH
    injector = ReplayInjector([{'tool': 'create_purchase_order',
        'args': {'project_id': 'PROJ-A', 'quote_id': 'Q1', 'quantity': 10},
        'observed_result': {'po_id': 'PO-0001', 'status': 'DRAFT', 'vendor_id': 'V1',
            'quantity': 0, 'component_id': 'C-A', 'unit_price': 480.0, 'total': 5000.0, 'requires_approval': False},
        'fault_injected': 'corrupted_obs'}])
    result = run_episode(get_task('T01'), ListModel([
        call('create_purchase_order', project_id='PROJ-A', quote_id='Q1', quantity=10),
        call('release_order', po_id='PO-0001'), FINISH]), injector=injector, policy='A')
    assert result['oracle_pass'] and result['faults_injected'] == 1
    assert result['trajectory'][0]['observed_result']['quantity'] == 0
    assert result['trajectory'][0]['true_result']['quantity'] == 10
