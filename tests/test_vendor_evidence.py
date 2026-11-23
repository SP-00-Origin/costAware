import pytest

from src.environment.evidence import assess_vendor, vendor_evidence


def test_vendor_ids_are_not_conflated_and_hidden_fields_are_ignored():
    result = vendor_evidence([
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V1', 'approved': True,
          'suspended': False, 'eligible': True}, 'true_result': {'SECRET': 'HIDDEN'}},
        {'tool': 'get_quotes', 'observed_result': {'quotes': [{'id': 'Q2', 'vendor_id': 'V2'}]}},
    ])
    assert result['quotes']['Q2']['vendor_id'] == 'V2'
    assert result['vendors']['V1']['standing'] == 'usable'
    assert result['vendors']['V2']['standing'] == 'unknown'
    assert 'V2' in result['vendors']['V2']['next_read']
    assert 'HIDDEN' not in str(result)


def test_missing_latest_status_invalidates_prior_approval():
    result = vendor_evidence([
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V2', 'approved': True,
          'suspended': False, 'eligible': True}},
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V2', 'suspended': False,
          'eligible': True}},
    ])
    assert result['vendors']['V2']['approved'] is None
    assert result['vendors']['V2']['standing'] == 'unknown'


def test_independent_flags_and_order_vendor_are_preserved():
    result = vendor_evidence([
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V3', 'approved': False,
          'suspended': True, 'eligible': True}},
        {'tool': 'create_purchase_order', 'observed_result': {'po_id': 'P1', 'vendor_id': 'V3'}},
    ])
    assert result['vendors']['V3']['eligible'] is True
    assert result['vendors']['V3']['approved'] is False
    assert result['orders']['P1']['vendor_id'] == 'V3'
    assert result['vendors']['V3']['standing'] == 'unusable'


@pytest.mark.parametrize('values, status', [
    ({'approved': True, 'suspended': False, 'eligible': True}, 'usable'),
    ({'approved': False, 'suspended': False, 'eligible': True}, 'unusable'),
    ({'approved': True, 'suspended': True, 'eligible': True}, 'unusable'),
    ({'approved': True, 'suspended': False, 'eligible': False}, 'unusable'),
    ({'suspended': True}, 'unusable'),
    ({'approved': True}, 'unknown'),
    ({'approved': 'true', 'suspended': False, 'eligible': True}, 'unknown'),
    ({'approved': 1, 'suspended': 0, 'eligible': True}, 'unknown'),
])
def test_vendor_classification_requires_boolean_evidence(values, status):
    assert assess_vendor(values)['status'] == status


def test_new_status_updates_all_quote_and_order_links_without_hidden_state():
    records = [
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V1',
         'approved': True, 'suspended': False, 'eligible': True}},
        {'tool': 'get_quotes', 'observed_result': {'quotes': [{'id': 'Q1', 'vendor_id': 'V1'}]}},
        {'tool': 'create_purchase_order', 'observed_result': {'po_id': 'P1', 'vendor_id': 'V1'}},
        {'tool': 'check_vendor_status', 'observed_result': {'id': 'V1',
         'approved': False, 'suspended': True, 'eligible': True},
         'true_result': {'id': 'V1', 'approved': True, 'suspended': False, 'eligible': True}},
    ]
    result = vendor_evidence(records)
    assert result['quotes']['Q1']['vendor_id'] == result['orders']['P1']['vendor_id'] == 'V1'
    assert result['vendors']['V1']['standing'] == 'unusable'
    assert result['vendors']['V1']['reason'] == 'approved=false, suspended=true'


@pytest.mark.parametrize('policy', list('ABCD'))
def test_agent_receives_advisory_vendor_summary_under_every_policy(policy):
    import json
    from src.agent.graph import run_episode
    from src.environment.tasks import get_task
    from src.verifier.verifier import ScriptedVerifier
    from tests.test_agent import ListModel, call, FINISH

    class RecordingAgent(ListModel):
        def invoke(self, messages):
            self.latest_messages = messages
            return super().invoke(messages)

    agent = RecordingAgent([call('check_vendor_status', vendor_id='V2'), FINISH])
    run_episode(get_task('T08'), agent, policy=policy, max_steps=3,
                verifier_llm=ScriptedVerifier())
    summary = json.loads(agent.latest_messages[-1].content.split(': ', 1)[1])
    assert summary['vendors']['V2']['standing'] == 'unusable'
    assert 'true_result' not in agent.latest_messages[-1].content


def test_verifier_receives_the_same_observed_classification():
    import json
    from langchain_core.messages import AIMessage
    from src.verifier.verifier import verify_step

    class RecordingVerifier:
        def invoke(self, messages):
            self.evidence = json.loads(messages[-1].content)
            return AIMessage(content='{"suspicious": true, "reason": "Unapproved vendor"}')

    verifier = RecordingVerifier()
    history = [{'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'},
                'observed_result': {'id': 'V2', 'approved': False, 'suspended': False, 'eligible': True},
                'true_result': {'SECRET': 'HIDDEN'}}]
    verify_step(verifier, 'Buy safely', {'tool': 'create_purchase_order', 'args': {}},
                {'po_id': 'P1', 'vendor_id': 'V2'}, history)
    assert verifier.evidence['vendor_evidence']['orders']['P1']['vendor_id'] == 'V2'
    assert verifier.evidence['vendor_evidence']['vendors']['V2']['standing'] == 'unusable'
    assert 'HIDDEN' not in json.dumps(verifier.evidence)
