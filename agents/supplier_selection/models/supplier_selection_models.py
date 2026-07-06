"""Data models for the Supplier Selection Agent (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProcurementPolicy:
    """Procurement policies that govern supplier selection."""
    policy_id: str
    policy_name: str
    max_supplier_cost_variance: float  # Max % variance from lowest cost
    min_reliability_score: float  # Minimum reliability threshold
    max_lead_time_days: int  # Maximum acceptable lead time
    prefer_local_suppliers: bool
    require_multiple_suppliers: bool  # Dual/multi-source requirement
    preferred_supplier_ids: List[int]  # List of preferred suppliers


@dataclass
class SupplierEvaluation:
    """Evaluation of a supplier against a replenishment order."""
    supplier_id: int
    supplier_name: str
    order_id: str
    sku_id: int
    location_id: int
    unit_cost: float
    total_cost: float
    lead_time_days: int
    reliability_score: float
    policy_compliance: bool
    compliance_issues: List[str]
    risk_score: float  # 0-100: lower is better
    final_score: float  # 0-100: higher is better


@dataclass
class SupplierSelectionResult:
    """Final selected supplier for a replenishment order."""
    order_id: str
    sku_id: int
    location_id: int
    selected_supplier_id: int
    selected_supplier_name: str
    order_quantity: int
    unit_cost: float
    total_cost: float
    lead_time_days: int
    selection_rationale: str
    policy_compliant: bool
    backup_supplier_id: Optional[int] = None
    backup_supplier_name: Optional[str] = None
    approval_required: bool = False  # True if high-cost or policy exception


@dataclass
class SupplierSelectionSummary:
    """Summary of supplier selection results."""
    total_orders_evaluated: int
    total_orders_selected: int
    total_procurement_cost: float
    policy_compliant_orders: int
    orders_requiring_approval: int
    average_lead_time: float
    supplier_diversity: int  # Number of unique suppliers used
    cost_savings_vs_initial: float  # Dollar savings from negotiations
    selections: List[SupplierSelectionResult]
    exceptions: List[dict]  # Orders with policy exceptions


@dataclass
class SupplierPerformanceScore:
    """Performance metrics for supplier scoring."""
    supplier_id: int
    supplier_name: str
    on_time_delivery_rate: float
    quality_score: float
    defect_rate: float
    financial_stability_score: float
    compliance_status: str  # "COMPLIANT", "AT_RISK", "NON_COMPLIANT"
    overall_score: float  # Composite score 0-100
