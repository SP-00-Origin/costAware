# Project experiments and dashboard

Start the interactive research dashboard from the repository root.

```powershell
python experiments/dashboard_server.py
```

Open the printed local address, normally `http://127.0.0.1:8765`. Choose a saved config to run an experiment. The Console view shows the equivalent command, episode progress, and the exit status. Use Saved runs to inspect the calculation, reliability chart, matched comparisons and traces, rebuild analysis, or download the JSONL record. The dashboard reads configs from `experiments/configs` and runs from the project's `output` and `logs` directories. Keep the server running while using the command controls.

To run the same experiment directly in the terminal:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase7_smoke.json
```

New runs go under `output/experiments` by default. Open `output/dashboard.html` for an offline archive of saved results, with scripted runs labeled.

Rebuild the project overview or regenerate an individual run from its JSONL log:

```powershell
python experiments/run_experiment.py --dashboard
python experiments/run_experiment.py --from-log path/to/events.jsonl
```

Use a copy of the JSON config with `provider` set to `gemini` for a live run. Set `GEMINI_API_KEY` or `GOOGLE_API_KEY` locally. Set `model` and optionally `verifier_model` to freeze the models. Each task and fault seed is shared across the configured policies. Agent decisions can still vary between live runs.

Overall success counts oracle passes from completed episodes over all planned episodes. Fault-conditioned metrics use completed faulted episodes. Selection rate uses original agent actions selected for verification. Verifier calls include rechecks after recovery. Completed matched pairs are compared against Policy B separately. A task-level bootstrap estimates uncertainty in the success-rate difference.

An interrupted log retains the planned grid and records which episodes started. Steps are flushed after their episode returns, so a process interrupted during a model call can leave an incomplete trace. Token counts rely on provider usage metadata. Monetary billing estimates and provider-side cost limits are outside this harness.

For a local Qwen pilot, keep Ollama running with `qwen3:8b` downloaded, then run:

```powershell
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_pilot.json
```

The `ollama` provider uses the native `http://127.0.0.1:11434/api/chat` endpoint
without a cloud API key. Agent and verifier use separate clients for the configured
local model. Thinking is disabled by default, and the verifier requests JSON output.
Local requests explicitly allocate 8192 context tokens by default. `model_options`
can configure `context_length`, `agent_max_tokens`, `verifier_max_tokens`,
`temperature`, `model_seed`, `thinking`, and `timeout_s`. Defaults bound each agent
response to 2048 tokens and each verifier response to 1024 tokens. These are
operational limits, not API quotas or the model's maximum supported context.
Check `ollama ps` to inspect actual loading. Groq and Gemini configs remain available.

Matched validation configs are `phase8_ollama_validation_clean.json` and
`phase8_ollama_validation_faulted.json`. Each runs five tasks under A–D with the
same fault seed and generation settings. The model seed and fault seed are distinct.
This is validation, not the full baseline or a statistical superiority claim.

New JSONL headers retain full task snapshots, dataset/source hashes, resolved model
options and installed local-model identity. Prior logs keep their original oracle
outcomes when reports are rebuilt; rebuilding is not re-evaluation under new tasks.

Episode traces include a readable timeline generated directly from logs, with the
action, observation, selection reason, verifier reason, recovery instruction and
next recorded action. Offline audit columns show corruption and true-value changes;
these labels are never sent to the agent or verifier. Public model statements are
logged when supplied. Reports do not invent private reasoning or make model calls.
Report rebuilding uses local CPU, memory and disk only.

Finished episodes, oracle success and agent stopping reasons are distinct. Injection
labels measure corruption detection; warnings on uncorrupted observations can be
valid responses to genuine tool errors or historical conflicts. Recovery acceptance
by a verifier does not prove successful task repair. Counts accompany rates.

An optional `max_total_tokens` stops starting additional episodes after the recorded
usage reaches that budget. It is checked between episodes, can overshoot by an
episode, and cannot account for unavailable usage after failed calls. Remaining
outcomes are explicitly recorded as budget stops. It is not a hard provider spend
cap. Cloud models retain bounded response limits; local validation has no aggregate
token cap by default and retains the step and request-time limits.
