"""Policy Agent - centralized policy evaluation and reporting."""

from __future__ import annotations

import logging
from typing import List, Optional

from agents.supplier_selection.services.policy_evaluation_service import PolicyEvaluationService
from agents.supplier_selection.models import SupplierEvaluation

logger = logging.getLogger(__name__)


class PolicyAgent:
    """Agent to evaluate supplier assessments against procurement policies.

    This agent is intentionally lightweight and re-uses the existing
    PolicyEvaluationService from `supplier_selection` to remain consistent
    with established policy definitions.
    """

    def __init__(self, policy_service: Optional[PolicyEvaluationService] = None) -> None:
        self.policy_service = policy_service or PolicyEvaluationService()

    def execute(
        self,
        supplier_evaluations: List[SupplierEvaluation],
        policy_name: str = "STANDARD",
    ) -> dict[str, object]:
        """Evaluate a list of `SupplierEvaluation` records against a policy.

        Returns a dict with updated evaluations and a brief summary.
        """
        if not supplier_evaluations:
            logger.info("No supplier evaluations provided to PolicyAgent.execute")
            return {"evaluations": [], "summary": {"evaluated": 0, "compliant": 0, "non_compliant": 0}}

        updated: List[SupplierEvaluation] = []
        compliant_count = 0

        order_groups: dict[str, List[SupplierEvaluation]] = {}
        for ev in supplier_evaluations:
            order_key = ev.order_id or f"{ev.sku_id}:{ev.location_id}"
            order_groups.setdefault(order_key, []).append(ev)

        for order_key, order_evaluations in order_groups.items():
            lowest_cost_map: dict[str, float] = {}
            for ev in order_evaluations:
                key = f"{ev.sku_id}:{ev.location_id}"
                lowest_cost_map[key] = min(lowest_cost_map.get(key, ev.unit_cost), ev.unit_cost)

            evaluated_candidates: List[SupplierEvaluation] = []
            for ev in order_evaluations:
                key = f"{ev.sku_id}:{ev.location_id}"
                lowest_cost = lowest_cost_map.get(key, 0.0)
                updated_ev = self.policy_service.execute(ev, policy_name=policy_name, lowest_cost=lowest_cost)
                evaluated_candidates.append(updated_ev)

            selected_ev = sorted(
                evaluated_candidates,
                key=lambda ev: (
                    0 if ev.policy_compliance else 1,
                    -ev.final_score,
                    ev.total_cost,
                ),
            )[0]

            if selected_ev.policy_compliance:
                compliant_count += 1
            updated.append(selected_ev)

        summary = {
            "evaluated": len(updated),
            "compliant": compliant_count,
            "non_compliant": len(updated) - compliant_count,
        }

        return {"evaluations": updated, "summary": summary}
