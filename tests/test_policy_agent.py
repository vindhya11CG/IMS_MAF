"""Unit tests for the PolicyAgent and PolicyEvaluationService.

Phase 6: Added test verifying that high weather supply risk tightens the
effective reliability threshold during policy evaluation.
"""

from __future__ import annotations

from agents.policy_agent.agent import PolicyAgent
from agents.supplier_selection.models import SupplierEvaluation
from agents.supplier_selection.services.policy_evaluation_service import PolicyEvaluationService


def make_eval(supplier_id: int, name: str, sku: int, loc: int, unit_cost: float, reliability: float):
    return SupplierEvaluation(
        supplier_id=supplier_id,
        supplier_name=name,
        order_id=f"ORD-{supplier_id}",
        sku_id=sku,
        location_id=loc,
        unit_cost=unit_cost,
        total_cost=unit_cost * 10,
        lead_time_days=7,
        reliability_score=reliability,
        policy_compliance=False,
        compliance_issues=[],
        risk_score=10.0,
        final_score=50.0,
    )


def test_policy_agent_compliance():
    agent = PolicyAgent()

    # Two suppliers for the same sku/location: one low-cost compliant, one higher-cost failing reliability
    ev1 = make_eval(1, "GoodSupplier", sku=100, loc=1, unit_cost=10.0, reliability=0.90)
    ev2 = make_eval(2, "BadSupplier", sku=100, loc=1, unit_cost=12.0, reliability=0.60)

    result = agent.execute([ev1, ev2], policy_name="STANDARD")

    assert result["summary"]["evaluated"] == 2
    assert result["summary"]["compliant"] >= 1
    # Ensure updated evaluations include policy_compliance boolean
    evals = result["evaluations"]
    assert any(hasattr(e, "policy_compliance") for e in evals)


def test_policy_agent_weather_risk_tightens_reliability_threshold():
    """High weather supply risk (>0.6) must tighten the effective reliability
    threshold by 0.05.  A supplier that just passes the standard threshold
    (e.g. reliability=0.76 vs min=0.75) should FAIL under weather_supply_risk=0.8,
    because the effective minimum becomes min(1.0, 0.75+0.05)=0.80.
    """
    svc = PolicyEvaluationService()
    policy = svc.get_policy("STANDARD")  # min_reliability_score = 0.75

    supplier_eval = make_eval(
        supplier_id=10,
        name="MarginalSupplier",
        sku=999,
        loc=1,
        unit_cost=10.0,
        reliability=0.76,  # passes standard check (0.76 >= 0.75) but fails tightened (0.76 < 0.80)
    )

    # Standard evaluation — should pass
    is_compliant_standard, issues_standard = svc.evaluate_supplier(
        supplier_eval, policy, lowest_cost=10.0, weather_supply_risk=0.0
    )
    assert is_compliant_standard, (
        f"Expected compliance under standard conditions, got issues: {issues_standard}"
    )

    # High weather supply risk evaluation — should fail on reliability
    is_compliant_wx, issues_wx = svc.evaluate_supplier(
        supplier_eval, policy, lowest_cost=10.0, weather_supply_risk=0.8
    )
    assert not is_compliant_wx, (
        "Expected non-compliance under high weather supply risk (reliability too low)"
    )
    assert any("weather-adjusted" in issue.lower() or "weather_supply_risk" in issue for issue in issues_wx), (
        f"Expected weather risk explanation in compliance issues, got: {issues_wx}"
    )


def test_policy_agent_weather_risk_below_threshold_no_tightening():
    """Weather supply risk <= 0.6 must NOT tighten the reliability threshold."""
    svc = PolicyEvaluationService()
    policy = svc.get_policy("STANDARD")

    supplier_eval = make_eval(
        supplier_id=11,
        name="BarelyPassSupplier",
        sku=999,
        loc=2,
        unit_cost=10.0,
        reliability=0.76,
    )

    # weather_supply_risk = 0.5 (below 0.6 threshold) — should still pass
    is_compliant, issues = svc.evaluate_supplier(
        supplier_eval, policy, lowest_cost=10.0, weather_supply_risk=0.5
    )
    assert is_compliant, (
        f"Expected compliance when weather_supply_risk=0.5 (below threshold), got: {issues}"
    )


def test_policy_evaluation_service_backward_compat_no_weather_arg():
    """Calling execute() without weather_supply_risk must behave identically to before Phase 6."""
    svc = PolicyEvaluationService()
    supplier_eval = make_eval(1, "TestSupplier", sku=1, loc=1, unit_cost=10.0, reliability=0.90)
    result = svc.execute(supplier_eval, policy_name="STANDARD", lowest_cost=10.0)
    # Should not raise; compliance flag must be set
    assert isinstance(result.policy_compliance, bool)
    assert result.policy_compliance is True


def test_policy_agent_summarizes_selected_option_per_order():
    """PolicyAgent should report compliance per order, not per raw candidate evaluation."""
    agent = PolicyAgent()

    compliant = make_eval(1, "GoodSupplier", sku=100, loc=1, unit_cost=10.0, reliability=0.95)
    compliant.order_id = "ORD-001"
    compliant.final_score = 95.0

    non_compliant = make_eval(2, "BadSupplier", sku=100, loc=1, unit_cost=12.0, reliability=0.60)
    non_compliant.order_id = "ORD-001"
    non_compliant.final_score = 40.0

    result = agent.execute([non_compliant, compliant], policy_name="STANDARD")

    assert result["summary"]["evaluated"] == 1
    assert result["summary"]["compliant"] == 1
    assert result["summary"]["non_compliant"] == 0
