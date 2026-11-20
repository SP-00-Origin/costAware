# Experiment setup changes

Updated: 2026-11-21. This records changes from the earlier harness through the
current local validation work. Design changes remain pending team review in
[decisions.md](../decisions.md). Generated run output is not part of the source changes.

## What stayed the same

- One procurement simulator, 17 tools, 20 hand-written tasks and policies A–D.
- A deterministic Python oracle checks true state; it is never an LLM.
- The agent and verifier receive observed results, not true results or fault labels.
- Faults are seeded by tool, arguments and occurrence. Matching seeds does not force
  live agents to choose identical actions across policies.
- Verification is after execution and advisory. A warning alone does not change
  the real state or make a failed task pass.

## Changes to the previous setup

| Area | Earlier behavior | Current behavior |
|---|---|---|
| Providers | Online providers and scripted tests | Groq/Gemini retained; local Qwen through Ollama added |
| Local transport | Initial OpenAI-compatible pilot | Native Ollama API with explicit context, output limits, seed and thinking setting |
| Task creation limits | Positive caps could reject cancelling a bad draft and replacing it | Positive caps removed from procurement tasks; explicit zero caps retained |
| Duplicate prevention | Oracle checks active duplicates | Retained; cancelled drafts do not count as active duplicates |
| Verifier evidence | Goal, action, observation and history | Adds tool contracts and the same observable diagnostics under B/C/D |
| Verifier guidance | Could mistake ordinary progress for an error | Explains valid intermediate states and approval/release transitions |
| Recovery | Suspicious reads could repeat unchanged invalid arguments | Persistent argument errors request correction; transient read failures can retry once |
| Agent instructions | General procurement workflow | Clarifies vendor properties, grounded IDs, completion and approval versus release |
| Reports | Metrics and raw JSON traces | Adds readable step timelines while retaining raw records |
| Diagnostic labels | False-positive terminology could suggest every warning was wrong | Explains injection-label rates, genuine tool errors and historical conflicts |
| Provenance | Earlier logs lack complete runtime/task identity | New headers retain task snapshots, dataset/source hashes, resolved options and local model identity |

Cancellation fees were discussed and explicitly deferred. The oracle's implementation
was not changed to accept verifier opinions. It still evaluates configured task rules.

## What a readable report contains

Each episode shows its goal, oracle result, agent stopping reason and final statement.
For every tool call it shows the action/arguments, observed result, verification
selection reason, verifier verdict/reason, retry or replanning instruction, and next
recorded agent action. Offline audit columns show injected corruption and differences
from true results. These columns are not supplied to the models.

Report generation uses existing JSONL and local computation, with no extra model
calls. It does not invent the agent's private reasoning. A selected action, successful
detection, useful follow-up and successful task outcome are different events.

## Local settings and resource limits

The current validation configs use Qwen `qwen3:8b`, context 8192, agent/verifier
response limits 2048/1024, temperature 0, model seed 7, thinking disabled and request
timeout 180 seconds. The agent action limit is 30. Model seed and fault seed are distinct.

There is no aggregate token cap in the local validation configs. An optional
`max_total_tokens` guard stops starting further episodes after recorded usage reaches
the budget. It can overshoot by an episode and cannot count unavailable usage after
failed calls; it is not a hard financial cap. Online account quotas remain external.

## Validation evidence

| Check or run | Result |
|---|---|
| Full offline suite on 2026-11-21 | 387 tests passed |
| Task validator | All 20 references/negative sets valid |
| Phase 7 final smoke run `4d289b3ea7fb4bcfbd64b1354cf9d9f2` | 16/16 scripted episodes passed; unchanged metrics after rebuild; exact action replay |
| Clean Qwen run `85d027114e304d58b6165fcaa551016c` | Every policy passed 4/5 tasks |
| Faulted Qwen run `dc07f0703a9d4805ab481c482f8c99d0` | Every policy passed 4/5 tasks |
| New Qwen audit | All 40 trajectories and oracle diffs replayed from task snapshots |
| Controlled graph tests | Warning ignored or detection missed can end in FAIL; acting on a warning can end in PASS |

Clean verifier calls for A/B/C/D were 0/45/14/15; faulted calls were 0/71/19/27.
The controlled cases use stand-ins and are not additional Qwen performance results.
Generated artifacts are under `output/` in this checkout and are not distributed as
source. The two Qwen batches have one source-fingerprint difference: validation of
non-mapping model options. Their actual resolved options, prompts and graph match.

## Remaining limitations

- T18 fails even with clean observations: vendor/evidence tracking and verifier
  assertions remain unreliable. Zero provider errors does not mean zero reasoning errors.
- Faulted T18/B reported five calls near the 8192 context limit. Usage warnings do
  not establish exactly which content was lost.
- Five tasks and one seed do not establish policy superiority. Multiple changes were
  made together, so old/new pilots cannot isolate one change's causal effect.
- Finished episodes, oracle success, fault detection and recovery acceptance must be
  interpreted separately. Uncorrupted observations can still warrant suspicion.
- Monetary billing estimates, hard spend enforcement and a full cost-versus-budget
  analysis are not complete features of this harness.

See [Phase 7 checks and Phase 8 startup](../PHASE7_CHECKS_AND_PHASE8_START.md) for the
next gate. Preserve old logs and their stored oracle verdicts when rebuilding reports.
