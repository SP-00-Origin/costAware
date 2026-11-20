"""Controlled graph checks, not live-model reliability results."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from langchain_core.messages import AIMessage, HumanMessage
from src.agent.graph import run_episode
from src.environment.env import ProcurementEnv
from src.environment.tasks import get_task
from src.evaluation.oracle import oracle_check
from src.faults.replay import ReplayInjector
import pytest


class ControlledAgent:
    def __init__(self, obey_warning):
        self.obey_warning = obey_warning
        self.saw_warning = False
        self.chosen_quote = None
        self.index = 0
        self.actions = [
            ('check_vendor_status', {'vendor_id': 'V2', '_confidence': 0.2}),
            ('get_quotes', {'component_id': 'C-L', '_confidence': 0.95}),
        ]

    def invoke(self, messages):
        self.saw_warning = self.saw_warning or any(
            isinstance(message, HumanMessage) and 'Recovery evidence:' in message.content
            for message in messages)
        if self.index == 2:
            corrected = self.obey_warning and self.saw_warning
            self.chosen_quote = 'QL1' if corrected else 'QL2'
            if corrected:
                self.actions.append(('check_vendor_status', {'vendor_id': 'V1', '_confidence': 0.95}))
            self.actions.extend([
                ('create_purchase_order', {'project_id': 'PROJ-H', 'quote_id': self.chosen_quote,
                                           'quantity': 40, '_confidence': 0.95}),
                ('request_approval', {'po_id': 'PO-0001', 'requester': 'hiro', '_confidence': 0.95}),
                ('approve_order', {'approval_id': 'APR-0001', '_confidence': 0.95}),
                ('release_order', {'po_id': 'PO-0001', '_confidence': 0.95}),
                ('finish', {'status': 'done', 'summary': 'Controlled agent has stopped.'}),
            ])
        tool, args = self.actions[self.index]
        self.index += 1
        return AIMessage(content='', tool_calls=[{'name': tool, 'args': args,
                                                   'id': str(self.index)}])


class ControlledVerifier:
    def __init__(self, detect):
        self.detect = detect

    def invoke(self, messages):
        evidence = json.loads(messages[-1].content)
        observation = evidence['observed_result']
        vendor = observation.get('vendor_id') or observation.get('id')
        suspicious = self.detect and vendor == 'V2'
        reason = ('Vendor V2 is not approved or lacks a trustworthy suspension status; '
                  'check vendor standing and choose an approved, non-suspended supplier.'
                  if suspicious else 'Accepted in this controlled test.')
        return AIMessage(content=json.dumps({'suspicious': suspicious, 'reason': reason}))


@pytest.mark.parametrize('policy', list('ABCD'))
@pytest.mark.parametrize('obey,detect', [(False, True), (True, True), (True, False)])
def test_selected_detected_and_acted_on_are_separate(policy, obey, detect):
    task = get_task('T08')
    fault = ReplayInjector([{'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'},
                             'observed_result': {'id': 'V2', 'approved': False, 'eligible': True},
                             'fault_injected': 'missing_field'}])
    agent = ControlledAgent(obey)
    result = run_episode(task, agent, policy=policy, injector=fault, max_steps=12,
                         verifier_llm=ControlledVerifier(detect))
    assert result['oracle_pass'] == (policy != 'A' and obey and detect)
    if agent.chosen_quote == 'QL2':
        assert not result['oracle_diff']['vendor_standing']['pass']
    if policy != 'A' and detect:
        assert agent.saw_warning


def test_cancel_bad_draft_and_replace_is_allowed_without_active_duplicates():
    task = get_task('T08')
    assert 'max_new_orders' not in task.expected_final_state
    env = ProcurementEnv(task)
    for tool, args in [
        ('create_purchase_order', {'project_id': 'PROJ-H', 'quote_id': 'QL2', 'quantity': 40}),
        ('cancel_order', {'po_id': 'PO-0001'}),
        ('create_purchase_order', {'project_id': 'PROJ-H', 'quote_id': 'QL1', 'quantity': 40}),
        ('request_approval', {'po_id': 'PO-0002', 'requester': 'hiro'}),
        ('approve_order', {'approval_id': 'APR-0001'}),
        ('release_order', {'po_id': 'PO-0002'}),
    ]:
        assert 'error' not in env.call(tool, args)['true_result']
    assert oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)[0]


def test_explicit_no_new_orders_still_rejects_cancelled_creation():
    task = get_task('T14')
    assert task.expected_final_state['max_new_orders'] == 0
    env = ProcurementEnv(task)
    env.run_actions(task.reference_solution)
    quote = next(iter(env.true_state.quotes))
    env.call('create_purchase_order', {'project_id': 'PROJ-N', 'quote_id': quote, 'quantity': 1})
    env.call('cancel_order', {'po_id': 'PO-0001'})
    passed, diff = oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)
    assert not passed and not diff['max_new_orders']['pass']


def test_persistent_argument_error_replans_without_identical_retry():
    from tests.test_agent import ListModel, call, FINISH
    agent = ListModel([call('search_vendors', vendor_id='INVALID'), FINISH])
    result = run_episode(get_task('T08'), agent, policy='B',
                         verifier_llm=ListModel([AIMessage(content='{"suspicious":true,"reason":"Invalid args"}')]))
    assert result['recovery_attempts'] == 0
    assert result['trajectory'][0]['replan_requested']
    assert 'Correct the arguments' in result['trajectory'][0]['recovery_concern']


