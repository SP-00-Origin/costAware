# Cost-Aware Adaptive Verification for Long-Horizon LLM Agents

A research testbed that asks: can a tool-using LLM agent decide **when** to check its own actions, so it stays almost as reliable as checking every step while paying only a fraction of the cost?

The agent works in a simulated **enterprise procurement** world (vendors, quotes, budgets, purchase orders, approvals, invoices). Tool results are sometimes corrupted on purpose, and a hidden, non-LLM oracle checks whether the task really succeeded.

```text
Task → LangGraph agent → Tool → Fault injector → Policy A/B/C/D
     → (Self-verifier) → Recovery → Next step
     → Deterministic oracle → Logs → Metrics
```

Research project, 2026–27.

## Team

| Who | Role |
|---|---|
| Krish Sharma | Maintainer: reviews and merges every pull request into `main`. |
| Siddharth Ranka, Shivam | Team members. |

Following the plan, nobody is permanently assigned to one part; everyone should understand the whole pipeline.

## Status

Phases 0–4 are done: simulator, 20 tasks with oracle, fault injector, LangGraph agent. Next is Phase 5: self-verifier and recovery.
See [`PROGRESS.md`](PROGRESS.md).

```bash
pip install -r requirements.txt
python -m pytest tests -q                           # all tests, no API key needed
python scripts/validate_tasks.py                    # check the task dataset
python run_simulation.py --task T17 --rate 0.4      # pipeline demo, no LLM
python run_agent.py --task all --provider scripted  # agent graph dry run, no key
python run_agent.py --task all --provider groq      # real agent, needs GROQ_API_KEY in .env (after the Groq PR)
```

## Folders

| Folder | Contents |
|---|---|
| `src/environment/` | Procurement simulator, tools with risk tiers, task loader. |
| `src/evaluation/` | Deterministic oracle and task validation. |
| `src/faults/` | Fault injector and replay. |
| `src/agent/` | LangGraph agent, model providers, prompts, trajectory logging. |
| `src/policies/` | Verification policies A–D. |
| `src/verifier/` | Self-verifier. Empty until Phase 5. |
| `tasks/` | `build_tasks.py` (source of truth) and the generated `tasks.jsonl`. |
| `tests/` | pytest suite. |
| `scripts/` | Task validation and trigger-coverage scripts. |
| `experiments/`, `logs/`, `results/` | Experiment configs, run logs (not committed) and results. |
| `docs/` | The implementation plan, the list of decisions, Phase 1–4 notes, and the report. |
| `archive/` | Earlier notes. Reference only. |

## Verification policies

- **A, no verification:** never verifies.
- **B, always verify:** verifies after every action.
- **C, fixed schedule:** verifies every N steps.
- **D, adaptive:** verifies on high-risk actions, schema/sanity failures or low confidence.

## What is measured

Task success rate, fault recovery rate, error propagation, verification cost (tokens, calls, latency), and reliability against the verification budget.

## Contributing

Read [`repo_instructions.md`](repo_instructions.md) first.
