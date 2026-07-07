"""Demo runner to exercise PolicyAgent and print the policy summary block."""

from agents.policy_agent.agent import PolicyAgent
from agents.supplier_selection.models import SupplierEvaluation


def make_eval(supplier_id, name, sku, loc, unit_cost, reliability):
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


def main():
    agent = PolicyAgent()
    evals = [
        make_eval(1, "GoodSupplier", 100, 1, 10.0, 0.90),
        make_eval(2, "BadSupplier", 100, 1, 14.0, 0.60),
    ]

    result = agent.execute(evals, policy_name="STANDARD")
    ps = result.get("summary", {})

    print("\n" + "="*100)
    print("POLICY AGENT - RE-EVALUATION SUMMARY")
    print("="*100)
    print(f"Evaluated: {ps.get('evaluated')}")
    print(f"Compliant: {ps.get('compliant')}")
    print(f"Non-compliant: {ps.get('non_compliant')}")


if __name__ == '__main__':
    main()
