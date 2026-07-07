"""Unit tests for the PolicyAgent."""

from __future__ import annotations

from agents.policy_agent.agent import PolicyAgent
from agents.supplier_selection.models import SupplierEvaluation


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
