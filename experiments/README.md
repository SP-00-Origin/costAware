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
