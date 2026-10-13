"""
llm.py — Phase 4
Model factory for the agent.

  provider="gemini"     real Gemini via langchain-google-genai (needs GEMINI_API_KEY or GOOGLE_API_KEY)
  provider="anthropic"  real Claude via langchain-anthropic (needs ANTHROPIC_API_KEY)
  provider="openai"     real OpenAI via langchain-openai (needs OPENAI_API_KEY)
  provider="scripted"   deterministic stand-in that replays a task's reference solution
                        and then calls `finish`; used for tests, harness smoke runs and
                        as an open-loop (never adapts to observations) baseline.

Both expose bind_tools(tools) → object with invoke(messages) → AIMessage, which is all
the graph needs, so the graph never knows which one it is driving.
"""
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage

from ..environment.tools import TOOL_SPECS
from .prompts import FINISH_SPEC, FINISH_TOOL

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def get_default_model(provider: str = "gemini") -> str:
    env_model = os.environ.get("COSTAWARE_AGENT_MODEL")
    if env_model:
        return env_model
    p = provider.lower()
    if p in ("gemini", "google"):
        return DEFAULT_GEMINI_MODEL
    if p == "openai":
        return DEFAULT_OPENAI_MODEL
    return DEFAULT_ANTHROPIC_MODEL


DEFAULT_MODEL = os.environ.get("COSTAWARE_AGENT_MODEL", DEFAULT_GEMINI_MODEL)


def tool_schemas() -> List[Dict[str, Any]]:
    """Registry tools + finish, in the OpenAI-style function format LangChain accepts."""
    specs = dict(TOOL_SPECS)
    specs[FINISH_TOOL] = FINISH_SPEC
    return [{"type": "function",
             "function": {"name": name, "description": s["description"], "parameters": s["parameters"]}}
            for name, s in specs.items()]


def make_llm(provider: str = "gemini", model: Optional[str] = None, task=None,
             temperature: float = 0.0, max_tokens: int = 1024):
    """Return a tool-bound chat model ready for graph use."""
    provider = provider.lower()

    if provider in ("gemini", "google"):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set. "
                "Add GEMINI_API_KEY to your .env file or environment (or use --provider scripted for a dry run)."
            )
        from langchain_google_genai import ChatGoogleGenerativeAI
        target_model = model or get_default_model(provider)
        llm = ChatGoogleGenerativeAI(
            model=target_model,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
            max_retries=3,
        )
        return llm.bind_tools(tool_schemas())

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set (use --provider scripted for a dry run)")
        from langchain_anthropic import ChatAnthropic
        target_model = model or get_default_model(provider)
        llm = ChatAnthropic(model=target_model, temperature=temperature,
                            max_tokens=max_tokens, max_retries=3)
        return llm.bind_tools(tool_schemas(), parallel_tool_calls=False)

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set (use --provider scripted for a dry run)")
        from langchain_openai import ChatOpenAI
        target_model = model or get_default_model(provider)
        llm = ChatOpenAI(model=target_model, temperature=temperature,
                         max_tokens=max_tokens, max_retries=3)
        return llm.bind_tools(tool_schemas(), parallel_tool_calls=False)

    if provider == "scripted":
        if task is None:
            raise ValueError("scripted provider needs the task")
        return ScriptedChatModel(task.reference_solution)

    raise ValueError(f"Unknown provider {provider}")


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
