"""Phase 6 policy settings and cheap checks, using only offline observations."""
import copy

import pytest

from src.environment.env import ProcurementEnv
from src.environment.tasks import load_tasks
from src.environment.tools import HIGH_RISK_TOOLS, TOOL_SPECS
from src.policies.config import validate_policy_config
from src.policies.policies import _schema_fail, should_verify


def decide(policy, result, tool="check_budget", step=0, config=None, confidence=None):
    return should_verify(policy, {"tool": tool, "args": {}, "confidence": confidence},
                         result, [], step, config=config)


@pytest.fixture
def budget(sim):
    return sim.check_budget("BUD-A")


def test_config_defaults_and_input_are_independent():
    supplied = {"interval": 2}
    settings = validate_policy_config(supplied)
    assert settings == {"interval": 2, "confidence_threshold": 0.6}
    settings["interval"] = 8
    assert supplied == {"interval": 2}
    assert validate_policy_config() == {"interval": 3, "confidence_threshold": 0.6}


@pytest.mark.parametrize("config", [
    [], "bad", {"intervall": 3}, {"interval": None}, {"interval": True},
    {"interval": 0}, {"interval": -1}, {"interval": 2.0}, {"interval": "3"},
    {"confidence_threshold": None}, {"confidence_threshold": True},
    {"confidence_threshold": "0.6"}, {"confidence_threshold": -0.1},
    {"confidence_threshold": 1.1}, {"confidence_threshold": float("nan")},
    {"confidence_threshold": float("inf")},
])
def test_invalid_config_rejected(config):
    with pytest.raises(ValueError):
        validate_policy_config(config)


@pytest.mark.parametrize("policy,expected", [("A", (False, "no_verify")), ("B", (True, "always_verify"))])
def test_a_and_b_do_not_depend_on_result_or_risk(policy, expected):
    for tool in TOOL_SPECS:
        for result in (None, {}, {"error": "timeout"}, {"_confidence": 0}):
            assert decide(policy, result, tool=tool, step=2) == expected


@pytest.mark.parametrize("interval,expected", [(1, [0, 1, 2, 3, 4, 5, 6]), (2, [0, 2, 4, 6]),
                                               (3, [0, 3, 6]), (8, [0])])
def test_c_uses_configured_zero_based_schedule(interval, expected):
    checks = []
    for step in range(7):
        verify, reason = decide("C", None, step=step, config={"interval": interval})
        if verify:
            checks.append(step)
            assert reason == "fixed_schedule"
        else:
            assert reason == "no_trigger"
    assert checks == expected


@pytest.mark.parametrize("step", [None, True, -1, 1.5, "0"])
def test_invalid_agent_step_rejected(step):
    with pytest.raises(ValueError, match="step"):
        decide("C", {}, step=step)


def test_unknown_policy_rejected():
    with pytest.raises(ValueError, match="Unknown policy"):
        decide("Z", {})


@pytest.mark.parametrize("tool", sorted(HIGH_RISK_TOOLS))
def test_d_high_risk_trigger_takes_precedence(tool):
    assert decide("D", {"error": "timeout", "_confidence": 0}, tool) == (True, "high_risk_tool")


def test_d_schema_trigger_precedes_confidence(budget):
    budget["remaining"] = 17
    assert decide("D", budget, confidence=0.1) == (True, "schema_fail")


def test_d_threshold_is_strict_and_configurable(budget):
    assert decide("D", budget, confidence=0.6) == (False, "no_trigger")
    assert decide("D", budget, confidence=0.6,
                  config={"confidence_threshold": 0.7}) == (True, "low_confidence")
    assert decide("D", budget, confidence=0) == (True, "low_confidence")
    assert decide("D", budget, confidence=0,
                  config={"confidence_threshold": 0}) == (False, "no_trigger")
    assert decide("D", budget, confidence=1,
                  config={"confidence_threshold": 1}) == (False, "no_trigger")


@pytest.mark.parametrize("confidence", [None, True, "0.2", [], -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence_is_unavailable_not_a_crash(budget, confidence):
    assert decide("D", budget, confidence=confidence) == (False, "no_trigger")


def test_result_cannot_supply_or_override_action_confidence(budget):
    budget["_confidence"] = 0.1
    assert decide("D", budget) == (False, "no_trigger")
    assert decide("D", budget, confidence=0.9) == (False, "no_trigger")
    budget["_confidence"] = 1
    assert decide("D", budget, confidence=0.1) == (True, "low_confidence")


def test_missing_confidence_uses_other_triggers(budget):
    assert decide("D", budget) == (False, "no_trigger")
    del budget["allocated"]
    assert decide("D", budget) == (True, "schema_fail")


@pytest.mark.parametrize("result", [None, [], "raw text", {}, {"parse_error": True},
                                     {"timeout": True}, {"error": "failed"}])
def test_d_checks_malformed_and_failed_observations(result):
    assert decide("D", result) == (True, "schema_fail")


@pytest.mark.parametrize("value", [None, True, "20000", [], float("nan"), float("inf"), -1])
def test_bad_numeric_budget_values_trigger_without_crashing(budget, value):
    budget["remaining"] = value
    assert decide("D", budget) == (True, "schema_fail")


def test_budget_arithmetic_has_small_absolute_rounding_tolerance(budget):
    budget["remaining"] += 0.005
    assert decide("D", budget) == (False, "no_trigger")
    budget["remaining"] += 1
    assert decide("D", budget) == (True, "schema_fail")


def test_checks_accept_reference_observations_and_detect_missing_fields(sim):
    # The reference solutions exercise every tool except get_vendor_details.
    details = sim.get_vendor_details("V1")
    assert not _schema_fail("get_vendor_details", details)
    for field in details:
        damaged = dict(details)
        del damaged[field]
        assert _schema_fail("get_vendor_details", damaged)
    seen = {"get_vendor_details"}
    for task in load_tasks():
        env = ProcurementEnv(task)
        for action in task.reference_solution:
            tool = action["tool"]
            observed = env.call(tool, action.get("args", {}))["observed_result"]
            assert not _schema_fail(tool, observed), (task.id, tool, observed)
            seen.add(tool)
            for field in observed:
                if field == "not_found":  # optional compare_quotes detail
                    continue
                damaged = copy.deepcopy(observed)
                del damaged[field]
                assert _schema_fail(tool, damaged), (tool, field)
    assert seen == set(TOOL_SPECS)


@pytest.mark.parametrize("tool,result", [
    ("search_vendors", {"vendors": []}),
    ("get_quotes", {"component_id": "C-A", "quotes": []}),
    ("check_existing_orders", {"project_id": "PROJ-A", "orders": []}),
    ("compare_quotes", {"ranked_quotes": [], "not_found": ["missing"]}),
    ("request_discount", {"success": False, "reason": "Requested discount too large"}),
])
def test_valid_empty_lists_and_declined_discount_do_not_trigger(tool, result):
    assert decide("D", result, tool=tool) == (False, "no_trigger")


def test_nested_quote_fields_and_arithmetic_are_checked(sim):
    original = sim.get_quotes("C-A")
    for field in original["quotes"][0]:
        damaged = copy.deepcopy(original)
        del damaged["quotes"][0][field]
        assert decide("D", damaged, "get_quotes") == (True, "schema_fail")
    damaged = copy.deepcopy(original)
    damaged["quotes"][0]["total_price"] += 1
    assert decide("D", damaged, "get_quotes") == (True, "schema_fail")
    damaged["quotes"] = [None]
    assert decide("D", damaged, "get_quotes") == (True, "schema_fail")


def test_quote_expiry_consistency_and_used_quote_exception(sim):
    observed = sim.check_quote_validity("Q1")
    observed["expired"] = True
    assert _schema_fail("check_quote_validity", observed)
    observed["status"] = "USED"
    assert not _schema_fail("check_quote_validity", observed)
    observed.update(expired=False, current_step=100)
    assert _schema_fail("check_quote_validity", observed)


def test_contradictory_vendor_status_and_boolean_type(sim):
    observed = sim.check_vendor_status("V1")
    observed["suspended"] = True
    assert decide("D", observed, "check_vendor_status") == (True, "schema_fail")
    observed["suspended"] = "false"
    assert decide("D", observed, "check_vendor_status") == (True, "schema_fail")


def test_quote_ranking_must_match_observed_prices(sim):
    observed = sim.compare_quotes(["Q1", "Q2"])
    observed["ranked_quotes"].reverse()
    assert decide("D", observed, "compare_quotes") == (True, "schema_fail")


def test_policy_does_not_mutate_inputs_or_need_hidden_state(budget):
    action = {"tool": "check_budget", "args": {"budget_id": "BUD-A"}}
    history = [{"tool": "check_budget", "observed_result": budget}]
    config = {"interval": 2}
    before = copy.deepcopy((action, budget, history, config))
    assert should_verify("D", action, budget, history, 0, config=config) == (False, "no_trigger")
    assert (action, budget, history, config) == before
