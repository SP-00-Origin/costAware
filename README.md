# Cost-Aware Adaptive Verification for Long-Horizon LLM Agents

## Problem statement

Tool-using language-model agents can make poor decisions when tools return missing,
incorrect or misleading information. Checking every action may improve reliability,
but adds model calls, tokens and latency. Checking nothing is cheaper but may allow
errors to affect later decisions.

This project asks: **can an agent select when to verify, approaching the reliability
of checking every action while using fewer verification resources?** Policy D is the
proposed adaptive method. Its advantage must be measured, not assumed.

## Experimental setup and policies

The environment is a synthetic enterprise procurement simulator with vendors,
quotes, budgets, purchase orders, approvals and invoices. It has 17 tools and 20
hand-written tasks across easy, medium and hard tiers.

Each policy uses the same task definitions, agent prompt, tools and configured
model settings. Fault seeds are matched across policies. Different agent decisions
can still produce different action paths and numbers of faults.

| Policy | When verification is selected |
|---|---|
| **A — Never verify** | No separate verifier calls. |
| **B — Always verify** | After every original agent action. |
| **C — Fixed schedule** | Every configured interval; interval 3 checks actions 1, 4, 7, and so on. |
| **D — Adaptive** | High-risk actions, observed schema/sanity failures, or low self-reported action confidence. |

B/C/D use a separate, tool-free verifier model instance. Selected actions and actual
verifier calls are counted separately because recovery checks add calls. Confidence
is requested with the action; it does not require an extra model call.

## How experiments run in simulation

```text
Task goal -> agent chooses an action -> simulator executes it
          -> seeded fault injector produces the observed result
          -> policy selects or skips verification
          -> verifier / read retry / replanning when applicable
          -> agent's next action
          -> deterministic oracle -> JSONL -> metrics and dashboard
```

The simulator keeps the **true state**. The agent and verifier see only observed
results; observations may be corrupted without directly changing the true state.
Faults can change the final outcome indirectly by changing the agent's decisions.
Some faults are harmless for a particular task, so an injected fault does not
automatically imply task failure.

Verification happens after execution and provides advice. Suspicious reads may be
retried once; persistent argument errors request correction. Suspicious writes
request a state check and replanning rather than an automatic repeated write.

The oracle is ordinary Python, never an LLM. It checks the true final state against
task requirements and rules such as budget, vendor standing, quote validity and
active duplicates. Oracle PASS is different from the agent claiming it is done.
Cancelled drafts may be replaced unless a task explicitly forbids creating orders.
Cancellation fees are not implemented.

## Available model providers

Provider IDs below are the exact values accepted by `--provider` and experiment configs.

| Provider ID | Execution | Model configured in this repository | Requirement |
|---|---|---|---|
| `groq` | Online API | Default `llama-3.3-70b-versatile`; pilot uses `openai/gpt-oss-20b` | `GROQ_API_KEY` |
| `gemini` | Online API | `gemini-3.1-flash-lite` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| `ollama` | Local model server | Qwen 3, `qwen3:8b` | Ollama running and model downloaded; no cloud key |
| `scripted` | Offline deterministic stand-in | Task reference actions | No key; engineering tests only |
| `anthropic` | Online API | `claude-haiku-4-5` | `ANTHROPIC_API_KEY` |
| `openai` | Online API | `gpt-4o-mini` | `OPENAI_API_KEY` |

These are repository defaults, not promises that an online account has access to
every model. Use `--model` for a single run, or `model` and `verifier_model` in a
config, to choose explicit model IDs. Keep keys in the ignored `.env` file or shell
environment. Model defaults can also be overridden by `COSTAWARE_AGENT_MODEL`.

## Quick start

Run from the repository root in PowerShell. Python 3.11 is used in the validated
`costaware_env` environment.

```powershell
conda activate costaware_env
cd D:\costAware
python -m pip install -r requirements.txt
python -m pytest tests -q
python scripts/validate_tasks.py
```

If the environment does not exist, create it first with
`conda create -n costaware_env python=3.11 pip`.

Run the complete offline harness check, then start the dashboard:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase7_smoke.json
python experiments/dashboard_server.py
```

Open **http://127.0.0.1:8765** and keep the server terminal running. Choose a config
to start a batch or a saved run to inspect results. Single-agent and batch commands
are collected in [the command guide](docs/RUN_COMMANDS.md).

For local Qwen, follow [the Ollama setup guide](docs/OLLAMA_SETUP.md), then run:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_validation_clean.json
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_validation_faulted.json
```

## Results and interpretation

New batches write `events.jsonl`, `summary.json`, `paired.json` and `dashboard.html`
under `output/experiments/<run_id>/`. `output/dashboard.html` indexes saved reports.
New logs retain task snapshots, resolved settings and model/source identifiers.

Readable episode timelines show actions, observations, selection reasons, verifier
reasons, recovery instructions and subsequent recorded actions. Fault labels and
true-value differences are offline audit data, never model inputs. Reports are
generated from logs without additional LLM calls or invented private reasoning.

Interpret the metrics together:

- **Oracle success:** successful true final states divided by planned episodes.
- **Selection rate:** original actions chosen for verification divided by original actions.
- **Trigger recall:** corrupted original actions selected divided by corrupted original actions.
- **Verifier false negatives:** checked corrupted observations accepted as safe.
- **Warnings on uncorrupted results:** injection-label false positives; some warnings
  are justified by real tool errors or conflicts with earlier observations.
- **Workload:** verifier calls, tokens, latency and recovery tool calls.

An episode finishing is not proof of task success. A faulted episode passing is not
proof that recovery repaired a fault. Monetary billing estimates and hard provider
spend caps are outside the current harness. The optional total-token budget is
checked between episodes and can overshoot by an episode.

## Project status

The original Section 10 Phase 7 harness gate passed on **2026-11-21**: 387 tests,
20 validated tasks, and a 16-episode scripted batch whose reports rebuild and whose
actions replay exactly. This validates engineering, not live-model reliability.

Phase 8 has pilot runs but no completed full research baseline. In the latest
five-task local validation, every policy passed 4/5 tasks in both clean and faulted
conditions. T18 failed even without injected faults; faulted T18/B also approached
the configured 8192-token context capacity. Review those limitations before freezing
a larger study. See [Phase 7 checks and Phase 8 startup](docs/PHASE7_CHECKS_AND_PHASE8_START.md)
and [PROGRESS.md](PROGRESS.md).

## Documentation and folders

| Location | Purpose |
|---|---|
| [docs/edits/EXPERIMENT_SETUP_CHANGES.md](docs/edits/EXPERIMENT_SETUP_CHANGES.md) | Changes from the earlier experiment setup and remaining limits |
| [docs/OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md) | Install Ollama, store models on D:, download Qwen and troubleshoot |
| [docs/RUN_COMMANDS.md](docs/RUN_COMMANDS.md) | Commands for tests, simulation, agents, batches, reports and dashboard |
| [docs/decisions.md](docs/decisions.md) | Design decisions and changes pending team review |
| `src/environment/`, `tasks/` | Simulator, tools and task definitions |
| `src/agent/`, `src/policies/`, `src/verifier/` | Agent, timing policies and verification/recovery |
| `src/faults/`, `src/evaluation/` | Seeded faults, oracle, metrics, analysis and readable reports |
| `experiments/`, `scripts/`, `tests/` | Configs, batch runner, utilities and automated checks |

## Team and contribution


members. Read [repo_instructions.md](repo_instructions.md) before contributing.
Never commit keys or generated run output. AI assistants never push; the user pushes.
