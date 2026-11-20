# Run commands

Run these commands from the repository root in PowerShell. Replace `D:\costAware`
if your clone is elsewhere. Commands are independent unless a section says otherwise.
Generated outputs should not be committed.

## Environment and dependencies

```powershell
conda activate costaware_env
cd D:\costAware
python --version
python -m pip install -r requirements.txt
```

For a new environment only: `conda create -n costaware_env python=3.11 pip`.

## Automated checks

```powershell
python -m pytest tests -q
python scripts/validate_tasks.py
```

The test suite runs offline without API keys. To avoid a pytest cache permission
warning, use `python -m pytest tests -q -p no:cacheprovider`.

Focused controls:

```powershell
python -m pytest tests/test_decision_controls.py tests/test_local_validation.py -q
python -m pytest tests/test_experiment.py -q
```

## Simulator only

```powershell
python run_simulation.py --task T17 --seed 7 --rate 0.25
```

This replays reference actions under A–D. It does not call an LLM or adapt to
observations. Verification selections are displayed, but this entry point does not
execute the graph's verifier/recovery loop. Use it to inspect simulator/fault plumbing.

## Scripted agent graph

```powershell
python run_agent.py --task T01 --provider scripted --policy A --seed 7 --fault-rate 0
python run_agent.py --task all --provider scripted --policy D --seed 7 --fault-rate 0.25
```

The scripted agent replays reference actions; its verifier notices explicit errors.
This exercises graph plumbing without model/API costs, not live-model reliability.
Single-agent logs go under `logs/` by default and do not automatically become harness
dashboard runs. Use the batch runner below for dashboard experiment records.

## Offline recovery and policy demonstrations

```powershell
python scripts/demo_recovery.py
python scripts/demo_policies.py --task T01 --seed 7 --fault-rate 0.25
python scripts/demo_policies.py --task T01 --interval 3 --confidence-threshold 0.6
```

The recovery demo uses a fixed misleading budget. The policy demo compares A–D
with deterministic stand-ins. Neither is a live research result.

## Single episodes with real models

Set the relevant key in `.env` or the shell for online providers. Keep keys out of
commits and command histories. Ollama needs a running local server and downloaded model.

```powershell
python run_agent.py --task T01 --provider ollama --model qwen3:8b --policy D --seed 7 --fault-rate 0.25
python run_agent.py --task T01 --provider groq --model openai/gpt-oss-20b --policy D --seed 7 --fault-rate 0.25
python run_agent.py --task T01 --provider gemini --model gemini-3.1-flash-lite --policy D --seed 7 --fault-rate 0.25
```

Groq uses `GROQ_API_KEY`; Gemini uses `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
Other supported providers are `anthropic` and `openai`, with their corresponding keys.
Online model availability depends on your account. Commands may incur provider usage.

Use `--fault-rate 0` for a clean episode, `--policy A/B/C/D` to select a policy,
`--max-steps 30` to bound original actions, and `--verifier-model MODEL_ID` to choose
a separate verifier model on the same provider. `--task T01,T11` selects multiple tasks.
`--log-dir logs/my_run` chooses a log directory. Add `-v` for observed/true audit output.

## Batch experiments and dashboard reports

Offline Phase 7 check:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase7_smoke.json
```

Local Qwen pilot and matched clean/faulted validation:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_pilot.json
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_validation_clean.json
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_validation_faulted.json
```

Online pilots, only when credentials and provider access are ready:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase8_groq_pilot.json
python experiments/run_experiment.py --config experiments/configs/phase8_gemini_pilot.json
```

The existing Gemini baseline config contains 20 tasks × 4 policies × 3 seeds = 240
episodes. Run it only after completing the [Phase 8 readiness steps](PHASE7_CHECKS_AND_PHASE8_START.md):

```powershell
python experiments/run_experiment.py --config experiments/configs/phase8_gemini_baseline.json
```

Batches write to `output/experiments/<run_id>/`. Use `--output-root output/my_batches`
to choose another generated-output root. A successful command exit means configured
episodes returned without episode-level errors; inspect oracle success separately.

## Start the interactive dashboard

```powershell
python experiments/dashboard_server.py
```

Open `http://127.0.0.1:8765`. Keep the terminal running. The dashboard lists saved
configs and runs, provides a command console, and displays readable episode timelines.

## Rebuild results from raw logs

Paste the run ID printed by the batch runner when prompted:

```powershell
$runId = Read-Host "Paste the run ID printed by the batch runner"
python experiments/run_experiment.py --from-log "output/experiments/$runId/events.jsonl"
python experiments/run_experiment.py --dashboard
```

The first regenerates `summary.json`, `paired.json` and the run dashboard. The second
rebuilds `output/dashboard.html`. Neither calls an LLM. Stored oracle verdicts are
preserved; report generation is not re-execution under current task rules.

## Fault-trigger coverage and task regeneration

```powershell
python scripts/trigger_coverage.py --seeds 50 --rate 0.25 --json output/coverage.json
```

Coverage is measured on reference trajectories without a live model. Its clean-step
selection counts are not a gold standard for unjustified verifier warnings.

Only after deliberately editing `tasks/build_tasks.py`, regenerate and validate:

```powershell
python tasks/build_tasks.py
python scripts/validate_tasks.py
```

Task regeneration changes the dataset. Do not run it as a way to revise historical
experiment outcomes.

## Local server commands

```powershell
ollama --version
ollama list
ollama pull qwen3:8b
ollama serve
ollama ps
ollama stop qwen3:8b
```

Do not start `ollama serve` if another server already owns port 11434. For D: storage
and installation instructions, use [OLLAMA_SETUP.md](OLLAMA_SETUP.md).
