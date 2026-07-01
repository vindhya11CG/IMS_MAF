"""Policy evaluation service for supplier selection."""

from __future__ import annotations

import logging
from typing import List, Optional

from .base_service import SupplierSelectionService
from ..models import ProcurementPolicy, SupplierEvaluation

logger = logging.getLogger(__name__)


class PolicyEvaluationService(SupplierSelectionService):
    """Evaluates suppliers against procurement policies."""

    def __init__(self) -> None:
        super().__init__(name="PolicyEvaluationService")
        self.policies: dict[str, ProcurementPolicy] = {}
        self._load_default_policies()

    def _load_default_policies(self) -> None:
        """Load default procurement policies."""
        # Standard procurement policy
        self.policies["STANDARD"] = ProcurementPolicy(
            policy_id="STANDARD",
            policy_name="Standard Procurement Policy",
            max_supplier_cost_variance=15.0,  # 15% variance from lowest cost
            min_reliability_score=0.75,
            max_lead_time_days=30,
            prefer_local_suppliers=False,
            require_multiple_suppliers=False,
            preferred_supplier_ids=[],
        )

        # Cost-optimized policy (aggressive pricing)
        self.policies["COST_OPTIMIZED"] = ProcurementPolicy(
            policy_id="COST_OPTIMIZED",
            policy_name="Cost-Optimized Policy",
            max_supplier_cost_variance=25.0,  # 25% variance allowed
            min_reliability_score=0.70,
            max_lead_time_days=45,
            prefer_local_suppliers=False,
            require_multiple_suppliers=False,
            preferred_supplier_ids=[],
        )

        # Risk-averse policy (dual sourcing, high reliability)
        self.policies["RISK_AVERSE"] = ProcurementPolicy(
            policy_id="RISK_AVERSE",
            policy_name="Risk-Averse Policy",
            max_supplier_cost_variance=10.0,  # 10% variance only
            min_reliability_score=0.85,
            max_lead_time_days=20,
            prefer_local_suppliers=True,
            require_multiple_suppliers=True,  # Require dual sourcing
            preferred_supplier_ids=[],
        )

        logger.info(f"Loaded {len(self.policies)} procurement policies")

    def evaluate_supplier(
        self,
        supplier_evaluation: SupplierEvaluation,
        policy: ProcurementPolicy,
        lowest_cost: float,
    ) -> tuple[bool, List[str]]:
        """
        Evaluate if a supplier meets policy requirements.
        
        Returns:
            (is_compliant, list_of_issues)
        """
        issues: List[str] = []

        # Check cost variance
        if lowest_cost > 0:
            cost_variance = ((supplier_evaluation.unit_cost - lowest_cost) / lowest_cost) * 100
            if cost_variance > policy.max_supplier_cost_variance:
                issues.append(
                    f"Cost variance {cost_variance:.1f}% exceeds policy limit of {policy.max_supplier_cost_variance}%"
                )

        # Check reliability
        if supplier_evaluation.reliability_score < policy.min_reliability_score:
            issues.append(
                f"Reliability score {supplier_evaluation.reliability_score:.2f} below minimum {policy.min_reliability_score}"
            )

        # Check lead time
        if supplier_evaluation.lead_time_days > policy.max_lead_time_days:
            issues.append(
                f"Lead time {supplier_evaluation.lead_time_days} days exceeds maximum {policy.max_lead_time_days}"
            )

        is_compliant = len(issues) == 0
        return is_compliant, issues

    def get_policy(self, policy_name: str = "STANDARD") -> ProcurementPolicy:
        """Get policy by name, defaults to STANDARD."""
        return self.policies.get(policy_name, self.policies["STANDARD"])

    def execute(
        self,
        supplier_evaluation: SupplierEvaluation,
        policy_name: str = "STANDARD",
        lowest_cost: float = 0.0,
    ) -> SupplierEvaluation:
        """
        Evaluate supplier against policy.
        
        Returns updated SupplierEvaluation with compliance info.
        """
        policy = self.get_policy(policy_name)
        is_compliant, issues = self.evaluate_supplier(supplier_evaluation, policy, lowest_cost)

        supplier_evaluation.policy_compliance = is_compliant
        supplier_evaluation.compliance_issues = issues

        if not is_compliant:
            logger.warning(
                f"Supplier {supplier_evaluation.supplier_name} (ID: {supplier_evaluation.supplier_id}) "
                f"has {len(issues)} policy violations for order {supplier_evaluation.order_id}"
            )

        return supplier_evaluation
