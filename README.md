# Cost-Aware Adaptive Verification for Long-Horizon LLM Agents

A research platform evaluating cost-effective, risk-triggered verification strategies for tool-using LLM agents executing long-horizon tasks within a **Synthetic Enterprise Procurement & Operations Environment**.

---

## 🎯 Research Objective

Investigate whether an autonomous LLM agent can dynamically determine *when* and *what* to verify—balancing task reliability against token cost, tool overhead, and execution latency compared to standard verification baselines.

---

## 🔄 Execution Pipeline

```text
Task Definition
  └── LLM Agent Execution
        └── Tool Invocation
              └── Controlled Fault Injection
                    └── Verification Policy Trigger
                          └── Self-Verification & Deterministic Checks
                                └── Error Recovery
                                      └── Hidden Oracle Evaluation & Trajectory Logging
```

---

## 📁 Repository Structure

```text
costaware/
├── docs/                 # Research notes and documentation
├── experiments/          # Experiment runners and evaluation pipelines
├── logs/                 # Trajectory and runtime execution logs
├── results/              # Output artifacts
│   ├── raw/              # Raw run logs and data dumps
│   ├── figures/          # Generated plots and visualizations
│   └── tables/           # Metric tables and summary reports
├── src/                  # Core framework source code
│   ├── environment/      # Enterprise procurement simulator, state, tools, oracle
│   ├── faults/           # Fault injection engine for agent observations
│   ├── agent/            # LLM agent definitions and prompt scaffolds
│   ├── verification/     # Self-verification checks and recovery routines
│   ├── policies/         # Verification policies (adaptive, fixed, baselines)
│   ├── graph/            # Workflow orchestration (LangGraph)
│   └── evaluation/       # Performance, cost, and reliability metrics
├── tasks/                # Benchmark scenarios and task datasets
│   └── scenarios/        # Enterprise procurement/operations scenarios
├── .gitignore
└── README.md
```

---

## ⚖️ Verification Policies

1. **Policy A (No Verification):** Executes tasks open-loop without verification.
2. **Policy B (Always Verify):** Verifies each tool call and state transition.
3. **Policy C (Fixed Schedule):** Verifies at predetermined step intervals.
4. **Policy D (Adaptive Verification):** Selectively verifies based on dynamic risk signals, cost thresholds, and uncertainty.

---

## 📊 Evaluation Dimensions

- **Task Success Rate:** End-to-end task completion against ground truth oracle.
- **Fault Recovery Rate:** Frequency of successful recovery from injected errors.
- **Error Propagation:** Downstream impact of undetected faults.
- **Verification Overhead & Cost:** Cumulative token cost, API calls, and end-to-end latency.
- **Pareto Efficiency:** Reliability curve relative to the verification budget.
