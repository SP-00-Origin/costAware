"""
prompts.py — Phase 4
Prompt scaffold for the procurement agent. The prompt is identical across
Policies A–D: only verification timing may differ between conditions.
"""
from ..environment.tasks import Task

FINISH_TOOL = "finish"

SYSTEM_PROMPT = """You are a procurement operations agent working inside a company's purchasing system.
You complete tasks by calling the tools provided — one tool call per turn. You cannot see the
system directly; you only see what each tool returns.

How to work:
- Use the IDs exactly as they appear in the task or in tool results. Never invent IDs.
- Gather the information you need before taking actions that change state (creating, modifying,
  approving, releasing or cancelling orders).
- Tool results come from live systems and are not always reliable: an answer can be incomplete,
  malformed, out of date or time out. Write actions have real effects even if their response is lost.
- Follow the company rules stated in the task.
- When the task is complete, call `finish` with a short summary. If you cannot complete it, call
  `finish` with status "gave_up" and explain why. Do not stop without calling `finish`."""

FINISH_SPEC = {
    "description": "Signal that you are done with the task.",
    "parameters": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["done", "gave_up"]},
            "summary": {"type": "string"},
        },
        "required": ["status", "summary"],
    },
}


def task_message(task: Task) -> str:
    return f"Task {task.id}: {task.goal}"
