# Ollama and local Qwen setup

This Windows guide runs Qwen 3 locally for costAware. Ollama is the model server;
`qwen3:8b` is the model. No Groq or Gemini key is needed for this provider.

## 1. Install the project environment

From the repository root, use the existing environment:

```powershell
conda activate costaware_env
cd D:\costAware
python -m pip install -r requirements.txt
```

For a new environment, run `conda create -n costaware_env python=3.11 pip` first.
The repository's native Ollama adapter uses the Python standard library; a separate
Python `ollama` package is not required.

## 2. Install Ollama

Download the Windows installer from the [official Ollama download page](https://ollama.com/download/windows),
run it, then open a new terminal and check:

```powershell
ollama --version
```

See [Ollama's Windows guide](https://docs.ollama.com/windows) for current system
requirements. Model loading depends on available memory; CPU execution may be slower.

## 3. Store model files on D:

Before downloading, quit Ollama from its system-tray icon. Run:

```powershell
New-Item -ItemType Directory -Force -Path "D:\Ollama\models"
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "D:\Ollama\models", "User")
$env:OLLAMA_MODELS = "D:\Ollama\models"
ollama serve
```

Leave this terminal running. The user variable persists for future sessions; the
shell assignment applies immediately. Restart an already-running server to apply
the new location. This changes model storage, not the application installation path.
These steps follow the [official model-location instructions](https://docs.ollama.com/windows#changing-model-location).

If port `127.0.0.1:11434` is already in use, another Ollama server is running. Quit
the tray application or stop the terminal's server before starting another. Do not
start two servers on the same port. Changing the variable does not migrate old models.

## 4. Download and check Qwen

In a second terminal:

```powershell
conda activate costaware_env
ollama pull qwen3:8b
ollama list
ollama run qwen3:8b
```

The [official model entry](https://ollama.com/library/qwen3:8b) lists the tool-capable
8B model at about 5.2 GB. Enter a short prompt to check it, then use `/bye` to leave
interactive chat. Download size is not the complete runtime memory requirement.

## 5. Run costAware locally

Keep the server running. From `D:\costAware` in `costaware_env`:

```powershell
python run_agent.py --task T01 --provider ollama --model qwen3:8b --policy D --seed 7 --fault-rate 0
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_validation_clean.json
python experiments/run_experiment.py --config experiments/configs/phase8_ollama_validation_faulted.json
```

The first command runs one real-model episode. Each validation batch runs five tasks
under four policies. These are validation runs, not the full Phase 8 baseline.

```powershell
python experiments/dashboard_server.py
```

Open `http://127.0.0.1:8765`, select a saved run and expand an episode timeline.

## 6. Understand local limits

The configs explicitly request 8192 context tokens, up to 2048 tokens per agent
response and 1024 per verifier response, temperature 0, model seed 7, thinking off,
and a 180-second request timeout. The graph allows 30 original agent actions.
There is no aggregate token cap in these local validation configs.

Context is the model's working capacity, not a cloud quota. Response and step limits
bound generation and execution. Larger context uses more memory; inspect loading with:

```powershell
ollama ps
```

Edit `model_options` in a copied experiment config to test a different context or
response limit. Keep settings matched across A–D, log them, and do not change them
mid-experiment. A larger context is not a guarantee of better reasoning.

## Troubleshooting

| Symptom | Check |
|---|---|
| `ollama` is not recognized | Reopen the terminal after installation and check the installer/PATH |
| Connection refused | Start the Ollama server and check port 11434 |
| Model not found | Run `ollama list`, then `ollama pull qwen3:8b` if needed |
| Models appear on C: | Confirm `OLLAMA_MODELS` and restart the server; do not redownload until the server uses the intended location |
| Port bind error | An Ollama server is already running; use it or quit it before restarting |
| Slow runs or memory pressure | Check `ollama ps`, GPU availability and the configured context |
| Near-context warnings | Inspect the trace; increase context only if memory allows, then validate again |
| Task FAIL | Read the oracle diff and timeline; a running model can still make incorrect decisions |

Use `ollama stop qwen3:8b` to unload the model. See the [CLI reference](https://docs.ollama.com/cli)
for server and model commands. Do not delete model files as a routine troubleshooting step.
