"""Local transport, response budgets, and reproducible report controls."""
import io
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.llm import make_llm, make_verifier_llm, model_settings
from src.agent.ollama import OllamaChatModel
from src.evaluation.trajectory import episode_story
from src.verifier.verifier import verify_step


def test_native_local_request_preserves_tools_context_and_usage(monkeypatch):
    recorded = []

    def respond(request, timeout):
        assert request.full_url == 'http://127.0.0.1:11434/api/chat'
        recorded.append(json.loads(request.data))
        return io.BytesIO(json.dumps({
            'message': {'content': '', 'tool_calls': [{'function': {
                'name': 'check_budget', 'arguments': {'budget_id': 'BUD-A'}}}]},
            'done_reason': 'stop', 'prompt_eval_count': 100, 'eval_count': 20,
        }).encode())

    monkeypatch.setattr('urllib.request.urlopen', respond)
    model = make_llm('ollama', options={'context_length': 8192, 'model_seed': 12})
    previous = AIMessage(content='', tool_calls=[{'name': 'check_budget',
        'args': {'budget_id': 'BUD-A'}, 'id': 'previous'}])
    reply = model.invoke([SystemMessage('rules'), HumanMessage('goal'), previous,
                          ToolMessage(content='{"remaining": 20}', tool_call_id='previous')])
    request = recorded[0]
    assert request['options']['num_ctx'] == 8192 and request['options']['seed'] == 12
    assert request['tools'] and request['think'] is False and request['stream'] is False
    assert request['messages'][-1]['tool_name'] == 'check_budget'
    assert request['messages'][-2]['tool_calls'][0]['function']['arguments'] == {'budget_id': 'BUD-A'}
    assert reply.tool_calls[0]['args'] == {'budget_id': 'BUD-A'}
    assert reply.usage_metadata['total_tokens'] == 120
    assert reply.response_metadata['finish_reason'] == 'tool_calls'


def test_local_verifier_json_request_and_length_reason(monkeypatch):
    def respond(request, timeout):
        body = json.loads(request.data)
        assert body['format'] == 'json' and 'tools' not in body
        return io.BytesIO(json.dumps({'message': {'content': '{}'}, 'done_reason': 'length',
                                     'prompt_eval_count': 8000, 'eval_count': 192}).encode())

    monkeypatch.setattr('urllib.request.urlopen', respond)
    reply = make_verifier_llm('ollama').invoke([HumanMessage('check')])
    assert reply.response_metadata['finish_reason'] == 'length'
    assert reply.response_metadata['near_context_limit']


@pytest.mark.parametrize('options', [
    {'context_length': 0}, {'context_length': 1024}, {'model_seed': True},
    {'thinking': 'false'}, {'agent_max_tokens': None}, {'temperature': float('nan')},
    {'unknown': 4}, {'timeout_s': -1},
])
def test_model_settings_reject_invalid_limits(options):
    with pytest.raises(ValueError):
        model_settings('ollama', options)


@pytest.mark.parametrize('options', [[], '', 1, False])
def test_model_options_must_be_mapping(options):
    with pytest.raises(ValueError):
        model_settings('ollama', options)


def test_verifier_gets_observable_contract_without_hidden_labels():
    class Recorder:
        def invoke(self, messages):
            body = json.loads(messages[-1].content)
            assert 'approved' in body['tool_contract']['required_result_fields']
            assert body['observable_checks']['schema_or_sanity_failed']
            assert 'HIDDEN' not in messages[-1].content
            return AIMessage(content='{"suspicious": true, "reason": "Missing approved."}')

    result = verify_step(Recorder(), 'goal', {'tool': 'check_vendor_status', 'args': {'vendor_id': 'V1'}},
                         {'id': 'V1', 'suspended': False, 'eligible': True},
                         [{'tool': 'x', 'args': {}, 'observed_result': {}, 'true_result': 'HIDDEN'}])
    assert result['verdict']['suspicious']


def test_readable_timeline_escapes_data_and_records_followup():
    episode = {'goal': '<script>goal</script>', 'status': 'completed', 'result': {
        'oracle_pass': False, 'done_reason': 'gave_up', 'final_summary': 'Could not finish',
        'oracle_diff': {'vendor_standing': {'pass': False}}}, 'trajectory': [
        {'step': 0, 'origin': 'agent', 'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'},
         'true_result': {'suspended': True}, 'observed_result': {}, 'fault_injected': 'missing_field',
         'verify_decision': True, 'trigger_reason': 'schema_fail',
         'verifier_verdict': {'suspicious': True, 'reason': 'Missing field'}, 'replan_requested': True,
         'recovery_concern': 'Recheck status'},
        {'step': 1, 'origin': 'agent', 'tool': 'check_vendor_status', 'args': {'vendor_id': 'V2'},
         'observed_result': {'suspended': True}, 'verify_decision': False}]}
    html = episode_story(episode)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'Next recorded agent action' in html and 'schema_fail' in html
    assert 'missing (true value true)' in html and 'Oracle FAIL' in html
    assert 'Missing field' in html and 'Recheck status' in html


def test_optional_batch_budget_retains_unstarted_outcomes_and_task_snapshot(tmp_path, monkeypatch):
    from pathlib import Path
    from experiments import run_experiment
    from src.evaluation.analysis import read_run
    from tests.test_agent import ListModel, FINISH
    from src.agent.llm import ScriptedChatModel

    class MeteredAgent(ScriptedChatModel):
        def invoke(self, messages):
            reply = super().invoke(messages)
            reply.usage_metadata = {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}
            return reply

    monkeypatch.setattr(run_experiment, 'make_llm',
                        lambda *args, task, **kwargs: MeteredAgent(task.reference_solution))
    config = run_experiment.load_config(Path('experiments/configs/phase7_smoke.json'))
    config.update(tasks=['T01'], policies=['A', 'B'], seeds=[7], max_total_tokens=1)
    log = run_experiment.run_batch(config, tmp_path / 'run', 'budget-test')
    header, episodes = read_run(log)
    assert episodes[0]['status'] == 'completed'
    assert episodes[1]['status'] == 'error' and episodes[1]['result']['budget_limit_reached']
    assert header['task_snapshots']['T01']['initial_state']
    assert header['runtime']['dataset_sha256']
