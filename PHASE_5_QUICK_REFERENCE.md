# Supplier Selection Agent (Phase 5) - Quick Reference

## Files Created
- `agents/supplier_selection/models/supplier_selection_models.py` - 5 dataclasses
- `agents/supplier_selection/services/policy_evaluation_service.py` - Policy enforcement
- `agents/supplier_selection/services/supplier_evaluation_service.py` - Scoring & evaluation
- `agents/supplier_selection/agent.py` - Main agent (15KB)
- `agents/supplier_selection/__init__.py` - Package exports
- Updated: `agent_orchestrator.py`, `main.py`, `agents/__init__.py`

## Key Features

### PolicyEvaluationService
```python
# 3 Built-in Policies:
STANDARD = 15% variance, 0.75 reliability, 30-day max
COST_OPTIMIZED = 25% variance, 0.70 reliability, 45-day max
RISK_AVERSE = 10% variance, 0.85 reliability, 20-day max, dual-source

# Check compliance:
is_compliant, issues = evaluate_supplier(supplier, policy, lowest_cost)
```

### SupplierEvaluationService
```python
# Calculates 3 Scores:
Performance = (On-Time×35%) + (Quality×30%) + (Low-Defect×20%) + (Financial×15%)
Risk = (Base×40%) + (Financial×20%) + (Compliance×25%) + (Geographic×15%)
Final = (Performance×70%) + ((100-Risk)×30%)

# Evaluate multiple suppliers:
evaluations = evaluate(supplier_ids, order_id, sku_id, costs_by_supplier)
```

### SupplierSelectionAgent
```python
# Execute supplier selection:
result = agent.execute(replenishment_orders)

# Output includes:
selections          # List of SupplierSelectionResult
summary             # SupplierSelectionSummary
azure_analysis      # Optional AI analysis
```

## Running

```bash
cd C:\Users\amitb\Desktop\IVM\IMS_MAF
python main.py
```

## Change Policy

```python
# In main.py:
orchestrator = AgentOrchestrator(
    openai_client=openai_client,
    supplier_policy="COST_OPTIMIZED"  # Change policy here
)
```

## Output Format

```
PHASE 5: SUPPLIER SELECTION SUMMARY
====================================
Orders Processed: 10
Supplier Selections Made: 10
Total Procurement Cost: $5,234.50
Policy Compliant Orders: 9
Orders Requiring Approval: 1
Supplier Diversity: 8 suppliers
Cost Savings vs Initial: $125.00
Average Lead Time: 14.2 days

POLICY EXCEPTIONS (1 order):
  - Order ORD-0001-001234-001: Selected XYZ Corp - cost variance 18% exceeds policy limit
```

## Data Flow

```
ReplenishmentOrder (from Phase 4)
    ↓
PolicyEvaluationService (check compliance)
    ↓
SupplierEvaluationService (score suppliers)
    ↓
Best Compliant Supplier Selected
    ↓
Backup Supplier Identified
    ↓
SupplierSelectionResult (to Phase 6)
```

## Metrics

- 35 suppliers evaluated
- 315 pricing tiers considered
- 420 performance metrics loaded
- 35 risk profiles assessed
- 3 procurement policies
- Multi-criteria scoring
- Dual-supplier support
- Policy exception tracking

## Policies Summary

| Metric | STANDARD | COST_OPT | RISK_AVERSE |
|--------|----------|----------|-------------|
| Cost Variance | 15% | 25% | 10% |
| Min Reliability | 0.75 | 0.70 | 0.85 |
| Max Lead Time | 30d | 45d | 20d |
| Dual Sourcing | No | No | Yes |
| Use Case | Balanced | Budget | Critical |

## Key Classes

### ProcurementPolicy
```python
policy_id: str
policy_name: str
max_supplier_cost_variance: float
min_reliability_score: float
max_lead_time_days: int
prefer_local_suppliers: bool
require_multiple_suppliers: bool
preferred_supplier_ids: List[int]
```

### SupplierSelectionResult
```python
order_id: str
selected_supplier_id: int
selected_supplier_name: str
order_quantity: int
unit_cost: float
total_cost: float
lead_time_days: int
selection_rationale: str
policy_compliant: bool
backup_supplier_id: Optional[int]
backup_supplier_name: Optional[str]
approval_required: bool
```

### SupplierSelectionSummary
```python
total_orders_evaluated: int
total_orders_selected: int
total_procurement_cost: float
policy_compliant_orders: int
orders_requiring_approval: int
average_lead_time: float
supplier_diversity: int
cost_savings_vs_initial: float
selections: List[SupplierSelectionResult]
exceptions: List[dict]
```

## Workflow Summary

```
PHASES 1-3: Risk Assessment (166K positions)
    ↓
PHASE 4: Order Generation (orders + costs)
    ↓
PHASE 5: Supplier Selection ← YOU ARE HERE
    ↓
PHASE 6: Approval & Notifications (future)
```

## Testing

All 5 phases tested end-to-end:
- ✅ Phase 1: Snapshots loaded and validated
- ✅ Phase 2: Stock calculations completed
- ✅ Phase 3: Risk assessments generated
- ✅ Phase 4: Orders generated with EOQ
- ✅ Phase 5: Suppliers selected with policies

---

**Status**: ✅ COMPLETE AND READY  
**Phases**: 1, 2, 3, 4, 5 (all integrated)  
**Next**: Phase 6 (Approval & Notifications)
