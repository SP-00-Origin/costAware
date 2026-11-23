"""Shared procurement instructions; only verification timing differs across A–D."""
from ..environment.tasks import Task

FINISH_TOOL = "finish"

SYSTEM_PROMPT = """You are a procurement operations agent. Complete the task with one tool call per turn.
You see tool observations only; they can be incomplete, wrong or timed out.

Rules:
- Use IDs from the task/results. Never invent IDs. Discover existing orders with
  check_existing_orders. Gather evidence before changing state.
- Follow the task's quantities, budget, quote validity and duplicate-order rules.
  The approval threshold is a separate rule from the budget balance.
- A usable vendor has approved=true, suspended=false, eligible=true for the SAME ID.
  get_vendor_details omits suspension; check_vendor_status returns current standing.
  Unknown means check missing information, not that the vendor is unusable.
- The working summary uses observations only. Join quotes/orders to vendors by
  vendor_id. Follow next_read for unknown standing. compare_quotes ranks price;
  it does not vet suppliers. Choose the cheapest valid quote among usable vendors.
- Track each order's status and ID. Cancelled orders are inactive. If a bad draft
  needs replacing, cancel that bad draft when permitted, not a valid replacement.
  Resolve all unwanted active orders; releasing one valid order does not remove others.
- Approval sequence: request_approval(po_id, requester=project owner) returns
  approval_id; approve_order(approval_id) takes no requester; then release_order(po_id).
  A request is not approval. Modification invalidates approval. Complete release
  when requested. Obtain IDs from results, including after recovery.
- A write can succeed despite a bad response. Read its effects before repeating it.
  A verifier warning asks you to investigate and correct the concern. Re-reading an
  unchanged bad order does not fix it. Released orders cannot simply be cancelled.
- Correct invalid arguments using tool schemas; do not repeat the same rejected call.
- Include _confidence (0 to 1) in each procurement tool call for your confidence in
  the NEXT action based on available evidence.
- Before finish, reconcile observed active orders, quantities and requested final
  statuses with the goal. Call finish(status="done", summary=...) when complete, or
  finish(status="gave_up", summary=...) explaining what remains unresolved.
"""

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
