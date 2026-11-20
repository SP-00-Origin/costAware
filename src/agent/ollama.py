"""Local Ollama chat adapter with explicit context and generation limits."""
import json
import urllib.request
from uuid import uuid4

from langchain_core.messages import AIMessage


class OllamaChatModel:
    def __init__(self, model, temperature=0.0, max_tokens=2048, context_length=8192,
                 model_seed=7, thinking=False, timeout_s=180, json_output=False):
        self.model = model
        self.tools = []
        self.json_output = json_output
        self.settings = dict(temperature=temperature, num_predict=max_tokens,
                             num_ctx=context_length, seed=model_seed)
        self.thinking = thinking
        self.timeout_s = timeout_s

    def bind_tools(self, tools, **kwargs):
        self.tools = tools
        return self

    def invoke(self, messages):
        history = []
        names = {}
        for message in messages:
            role = {'system': 'system', 'human': 'user', 'ai': 'assistant', 'tool': 'tool'}[message.type]
            item = {'role': role, 'content': message.content}
            if message.type == 'ai' and message.tool_calls:
                item['tool_calls'] = []
                for call in message.tool_calls:
                    names[call['id']] = call['name']
                    item['tool_calls'].append({'function': {'name': call['name'], 'arguments': call['args']}})
            if message.type == 'tool':
                item['tool_name'] = names.get(message.tool_call_id, message.name or '')
            history.append(item)
        body = dict(model=self.model, messages=history, options=self.settings,
                    think=self.thinking, stream=False)
        if self.tools:
            body['tools'] = self.tools
        if self.json_output:
            body['format'] = 'json'
        request = urllib.request.Request('http://127.0.0.1:11434/api/chat',
            data=json.dumps(body).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            result = json.load(response)
        reply = result['message']
        calls = []
        for call in reply.get('tool_calls', []):
            function = call['function']
            args = function['arguments']
            if isinstance(args, str):
                args = json.loads(args)
            calls.append({'name': function['name'], 'args': args, 'id': uuid4().hex})
        usage = dict(input_tokens=result.get('prompt_eval_count', 0),
                     output_tokens=result.get('eval_count', 0))
        usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
        reason = result.get('done_reason', 'stop')
        if calls and reason != 'length':
            reason = 'tool_calls'
        metadata = {'finish_reason': reason, 'context_length': self.settings['num_ctx'],
                    'near_context_limit': usage['total_tokens'] >= self.settings['num_ctx'] * 0.9,
                    'load_duration_ns': result.get('load_duration'),
                    'total_duration_ns': result.get('total_duration')}
        return AIMessage(content=reply.get('content', ''), tool_calls=calls,
                         usage_metadata=usage, response_metadata=metadata)


def local_model_metadata(model):
    """Record the installed model identity, without a generation call."""
    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as response:
        models = json.load(response)['models']
    for item in models:
        if item['name'] == model or item.get('model') == model:
            return {key: item.get(key) for key in ('name', 'digest', 'details', 'size')}
    raise ValueError(f'Local model {model} is not installed')
