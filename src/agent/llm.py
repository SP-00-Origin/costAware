"""
llm.py — Phase 4
Model factory for the agent.

  provider="anthropic"  real Claude via langchain-anthropic (needs ANTHROPIC_API_KEY)
  provider="groq"       open models on Groq via langchain-groq (needs GROQ_API_KEY),
                        default llama-3.3-70b-versatile
  provider="scripted"   deterministic stand-in that replays a task's reference solution
                        and then calls `finish`; used for tests, harness smoke runs and
                        as an open-loop (never adapts to observations) baseline.

Both expose bind_tools(tools) → object with invoke(messages) → AIMessage, which is all
the graph needs, so the graph never knows which one it is driving.
"""
import copy
import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from ..environment.tools import TOOL_SPECS
from .prompts import FINISH_SPEC, FINISH_TOOL

# Default model per provider. COSTAWARE_AGENT_MODEL overrides the default of whichever
# provider is used; --model overrides both.
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-3.1-flash-lite",
    "openai": "gpt-4o-mini",
    "scripted": "scripted-reference",
}
DEFAULT_MODEL = os.environ.get("COSTAWARE_AGENT_MODEL", DEFAULT_MODELS["anthropic"])


def default_model(provider: str) -> str:
    if provider == "scripted":
        return DEFAULT_MODELS["scripted"]
    return os.environ.get("COSTAWARE_AGENT_MODEL") or DEFAULT_MODELS[provider]


def tool_schemas() -> List[Dict[str, Any]]:
    """Add agent-only confidence without changing the simulator's tool registry."""
    specs = copy.deepcopy(TOOL_SPECS)
    schemas = []
    for name, spec in specs.items():
        spec["parameters"]["properties"]["_confidence"] = {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "Your confidence that this is the appropriate next action, before its result.",
        }
        spec["parameters"]["required"].append("_confidence")
        schemas.append({"type": "function", "function": {
            "name": name, "description": spec["description"], "parameters": spec["parameters"]}})
    schemas.append({"type": "function", "function": {
        "name": FINISH_TOOL, **copy.deepcopy(FINISH_SPEC)}})
    return schemas


def _make_chat_model(provider, model, temperature, max_tokens):
    """Create a provider model before assigning agent tools or verifier prompts."""
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY in the environment or .env")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model or default_model(provider), api_key=key,
                                     temperature=temperature, max_output_tokens=max_tokens,
                                     timeout=45, max_retries=2)
    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("Set OPENAI_API_KEY in the environment or .env")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model or default_model(provider), temperature=temperature,
                          max_tokens=max_tokens, max_retries=3)
    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set (use --provider scripted for a dry run)")
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=model or default_model("anthropic"), temperature=temperature,
                            max_tokens=max_tokens, max_retries=3)
        return llm
    if provider == "groq":
        if not os.environ.get("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY is not set (use --provider scripted for a dry run)")
        from langchain_groq import ChatGroq
        # Free-tier Groq keys have low tokens-per-minute limits; extra retries let the
        # client back off on HTTP 429 instead of ending the episode with an error.
        llm = ChatGroq(model=model or default_model("groq"), temperature=temperature,
                       max_tokens=max_tokens, max_retries=8, timeout=60)
        return llm
    raise ValueError(f"Unknown provider {provider}")


def make_llm(provider: str = "anthropic", model: Optional[str] = None, task=None,
             temperature: float = 0.0, max_tokens: Optional[int] = None):
    """Return a tool-bound chat model ready for graph use."""
    if provider == "scripted":
        if task is None:
            raise ValueError("scripted provider needs the task")
        return ScriptedChatModel(task.reference_solution)
    if max_tokens is None:
        max_tokens = 4096 if provider == "groq" else 1024
    llm = _make_chat_model(provider, model, temperature, max_tokens)
    if provider == "gemini":
        return llm.bind_tools(tool_schemas())
    return llm.bind_tools(tool_schemas(), parallel_tool_calls=False)


def make_verifier_llm(provider: str = "anthropic", model: Optional[str] = None):
    """Separate model instance without action tools; uses the existing provider libraries."""
    if provider == "scripted":
        from ..verifier.verifier import ScriptedVerifier
        return ScriptedVerifier()
    if provider == "groq" and (model or default_model(provider)).startswith("openai/gpt-oss-"):
        llm = _make_chat_model(provider, model, temperature=0.0, max_tokens=2048)
        return llm.bind(response_format={"type": "json_object"})
    return _make_chat_model(provider, model, temperature=0.0, max_tokens=512)


class ScriptedChatModel:
    """Replays a fixed action list, one tool call per turn, then calls finish.
    Position is derived from how many AI turns are already in the history, so it is stateless."""

    model_name = "scripted-reference"

    def __init__(self, actions: List[Dict[str, Any]]):
        self.actions = list(actions)

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages, **kwargs) -> AIMessage:
        i = sum(isinstance(m, AIMessage) for m in messages)
        if i < len(self.actions):
            a = self.actions[i]
            call = {"name": a["tool"], "args": dict(a.get("args", {})), "id": f"call_{i:03d}"}
        else:
            call = {"name": FINISH_TOOL, "args": {"status": "done", "summary": "Reference solution complete."},
                    "id": f"call_{i:03d}"}
        return AIMessage(content="", tool_calls=[call])
