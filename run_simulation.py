"""
run_simulation.py — Quick Start Demo (Phase 1 → 4)
Run this file to see the full pipeline working end-to-end:
  Task → Simulator → Fault Injector → Policy → Oracle → Log

Usage:
    python run_simulation.py

No LLM key needed — this runs the simulator + oracle fully deterministically.
The agent step is simulated with a hard-coded action sequence for demo purposes.
In Phase 4, replace the manual_agent_step() with the real LangGraph agent.
"""
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.environment.entities import (
    Vendor, Component, SupplierQuote, Project,
    Budget, QuoteStatus
)
from src.environment.state     import SimulatorState
from src.environment.simulator import ProcurementSimulator
from src.faults.injector       import FaultInjector
from src.policies.policies     import should_verify
from src.evaluation.oracle     import oracle_check


# ─── 1. Build a Task (what will normally come from tasks.jsonl) ───────────────

def build_task_001():
    """
    EASY Task: Buy 10 units of Component-A from Vendor-V1, within budget.
    Expected final state: PO created + RELEASED, budget not exceeded.
    """
    state = SimulatorState(
        vendors={
            "V1": Vendor(id="V1", name="TechParts Ltd", eligible=True, approved=True, suspended=False),
            "V2": Vendor(id="V2", name="BadVendor Inc",  eligible=False, approved=False, suspended=True),
        },
        components={
            "C-A": Component(id="C-A", name="Circuit Board Alpha",
                             category="electronics", reference_price=500.0,
                             required_qty=10, available_qty=50),
        },
        quotes={
            "Q1": SupplierQuote(id="Q1", vendor_id="V1", component_id="C-A",
                                unit_price=480.0, quantity=10,
                                expiry_days=20, shipping_cost=200.0,
                                status=QuoteStatus.ACTIVE),
        },
        projects={
            "PROJ-A": Project(id="PROJ-A", name="Project Alpha",
                              owner="alice", budget_id="BUD-A",
                              procurement_rules={"require_approval_above": 10000}),
        },
        budgets={
            "BUD-A": Budget(id="BUD-A", allocated=20000.0),
        },
    )

    expected_final_state = {
        "po_status":         "RELEASED",
        "vendor_id":         "V1",
        "budget_id":         "BUD-A",
        "approval_required": True,
        "no_suspended_vendor": True,
        "expected_quantity": 10,
    }

    return state, expected_final_state


# ─── 2. Simulate Agent Actions (Phase 4: replace with LangGraph) ──────────────

def simulated_agent_run(sim: ProcurementSimulator, injector: FaultInjector, policy: str):
    """
    Simulates what the LangGraph agent would do — a fixed action sequence.
    In Phase 4 this will be replaced by the real Claude-powered agent.
    Returns: (trajectory, po_id_created)
    """
    trajectory = []
    po_id = None

    def call_tool(tool_name: str, **kwargs):
        """Call simulator → inject fault → log step."""
        # Get TRUE result from simulator
        tool_fn    = getattr(sim, tool_name)
        true_result = tool_fn(**kwargs)
        # Inject fault
        observed_result, fault_type = injector.inject(tool_name, true_result)
        # Policy decision
        action = {"tool": tool_name, "args": kwargs}
        verify, reason = should_verify(
            policy  = policy,
            action  = action,
            result  = observed_result,
            history = trajectory,
            step    = sim.state.step,
        )
        step_log = {
            "step":               sim.state.step,
            "tool":               tool_name,
            "args":               kwargs,
            "true_result":        true_result,
            "observed_result":    observed_result,
            "fault_injected":     fault_type,
            "verify_triggered":   verify,
            "trigger_reason":     reason,
        }
        trajectory.append(step_log)
        sim.advance_step()
        return observed_result

    # ── Step-by-step procurement workflow ─────────────────────────────────────

    # 1. Search vendors
    call_tool("search_vendors")

    # 2. Check vendor V1 details
    call_tool("get_vendor_details", vendor_id="V1")

    # 3. Check vendor V1 status
    call_tool("check_vendor_status", vendor_id="V1")

    # 4. Get quotes for Component-A
    call_tool("get_quotes", component_id="C-A")

    # 5. Check budget
    call_tool("check_budget", budget_id="BUD-A")

    # 6. Compare quotes
    call_tool("compare_quotes", quote_ids=["Q1"])

    # 7. Create Purchase Order — HIGH RISK
    result = call_tool("create_purchase_order",
                       vendor_id="V1", component_id="C-A",
                       quantity=10, unit_price=480.0,
                       project_id="PROJ-A", shipping_cost=200.0)
    if "po_id" in result:
        po_id = result["po_id"]

    if po_id:
        # 8. Request approval
        call_tool("request_approval", po_id=po_id, requester="alice")

        # 9. Approve order — HIGH RISK
        # Find the approval ID from true state
        approval_id = list(sim.state.approvals.keys())[-1] if sim.state.approvals else None
        if approval_id:
            call_tool("approve_order", approval_id=approval_id)

        # 10. Release order — HIGH RISK
        call_tool("release_order", po_id=po_id)

    return trajectory, po_id


# ─── 3. Oracle Evaluation ─────────────────────────────────────────────────────

def run_experiment(policy: str = "D", fault_seed: int = 42, fault_rate: float = 0.25):
    print(f"\n{'='*60}")
    print(f"  TASK-001 | Policy={policy} | Fault Seed={fault_seed} | Rate={fault_rate}")
    print(f"{'='*60}")

    # Build task
    initial_state, expected = build_task_001()

    # Set up simulator + injector
    sim      = ProcurementSimulator()
    sim.load(initial_state)
    injector = FaultInjector(seed=fault_seed, fault_rate=fault_rate)

    # Run simulated agent
    trajectory, po_id = simulated_agent_run(sim, injector, policy)

    # Patch expected final state with actual po_id
    if po_id:
        expected["po_id"] = po_id

    # Oracle check (uses TRUE state, not what agent saw)
    oracle_pass, diff = oracle_check(sim.state, expected)

    # ── Print step-by-step log ─────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"{'Step':<5} {'Tool':<28} {'Fault':<22} {'Verify':<8} {'Reason'}")
    print(f"{'─'*60}")
    for s in trajectory:
        fault   = s['fault_injected'] or "—"
        verify  = "YES ✓" if s['verify_triggered'] else "no"
        print(f"{s['step']:<5} {s['tool']:<28} {fault:<22} {verify:<8} {s['trigger_reason']}")

    # ── Oracle result ──────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  ORACLE: {'✅ PASS' if oracle_pass else '❌ FAIL'}")
    print(f"{'─'*60}")
    for check, detail in diff.items():
        status = "✅" if detail["pass"] else "❌"
        print(f"  {status} {check:<25} expected={detail['expected']}  actual={detail['actual']}")

    verify_count = sum(1 for s in trajectory if s["verify_triggered"])
    print(f"\n  Verification overhead: {verify_count}/{len(trajectory)} steps "
          f"({100*verify_count//len(trajectory)}%)")
    print(f"{'='*60}\n")

    return oracle_pass, trajectory


# ─── 4. Main — Run All 4 Policies ─────────────────────────────────────────────

if __name__ == "__main__":
    SEED = 42

    results = {}
    for policy in ["A", "B", "C", "D"]:
        passed, traj = run_experiment(policy=policy, fault_seed=SEED, fault_rate=0.25)
        results[policy] = {"oracle_pass": passed, "steps": len(traj)}

    # Summary table
    print("\n" + "="*40)
    print("  SUMMARY — Policy Comparison")
    print("="*40)
    print(f"  {'Policy':<10} {'Oracle':<10} {'Steps'}")
    print("  " + "─"*30)
    for p, r in results.items():
        status = "PASS ✅" if r["oracle_pass"] else "FAIL ❌"
        print(f"  {p:<10} {status:<10} {r['steps']}")
    print("="*40)
