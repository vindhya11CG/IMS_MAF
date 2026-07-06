"""
Full Pipeline Integration Test
===============================
Run this ONLY AFTER tests/test_demand_forecast_agent.py passes (44/44).
This does not re-check demand-forecast internals; it verifies that the
Demand Forecast Agent, Inventory Monitoring Agent, Replenishment Planning
Agent, and Supplier Selection Agent all work together correctly through
orchestration/pipeline_orchestrator.py, with NO Azure OpenAI configured
(matches "must work without Azure" requirement).

Run from the repo root (demand_forecasting_system1/):

    python3 tests/test_full_pipeline_integration.py

Exits 0 on success, 1 on failure. No pytest dependency required.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("MODEL_PATH", "training_models/hybrid_model.pkl")
os.environ.setdefault("METRICS_PATH", "training_models/model_metrics.json")
# Keep this small for fast local/CI runs; raise it for a full batch check.
os.environ.setdefault("MAX_ML_FORECAST_CALLS", "25")

RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))
    return condition


def run():
    root = os.path.join(os.path.dirname(__file__), "..")

    model_path = os.path.join(root, os.environ["MODEL_PATH"])
    if not check(
        "trained model exists (run training_models/model_training.py first)",
        os.path.exists(model_path),
    ):
        _summarize()
        return

    from orchestration.pipeline_orchestrator import PipelineOrchestrator
    from agents.inventory_monitoring.models import RiskAssessment

    # ------------------------------------------------------------------
    # 1. Orchestrator boots without Azure
    # ------------------------------------------------------------------
    print("\n--- 1. Orchestrator boots without Azure configured ---")
    try:
        orchestrator = PipelineOrchestrator(use_azure=False)
        check("orchestrator initializes with use_azure=False", True)
    except Exception as e:
        check("orchestrator initializes with use_azure=False", False, str(e))
        _summarize()
        return

    # ------------------------------------------------------------------
    # 2. Full pipeline run
    # ------------------------------------------------------------------
    print("\n--- 2. Full pipeline run ---")
    try:
        result = orchestrator.run()
        check("pipeline.run() completes without raising", True)
    except Exception as e:
        check("pipeline.run() completes without raising", False, str(e))
        _summarize()
        return

    # ------------------------------------------------------------------
    # 3. Inventory Monitoring stage
    # ------------------------------------------------------------------
    print("\n--- 3. Inventory Monitoring stage ---")
    monitoring = result["monitoring"]
    assessments = monitoring["assessments"]
    check("monitoring produced at least one assessment", len(assessments) > 0)
    check(
        "assessments are RiskAssessment instances",
        all(isinstance(a, RiskAssessment) for a in assessments),
    )

    # ------------------------------------------------------------------
    # 4. forecast_demand -> forecasted_demand fix, verified end-to-end
    # ------------------------------------------------------------------
    print("\n--- 4. Field-name fix (forecasted_demand) ---")
    check(
        "RiskAssessment objects expose 'forecasted_demand'",
        all(hasattr(a, "forecasted_demand") for a in assessments),
    )
    check(
        "at least one row was actually enhanced with the ML forecast",
        result["assessments_enhanced_with_ml"] > 0,
        "0 rows enhanced - check that risk_detected rows exist and the "
        "trained model loads correctly",
    )

    # ------------------------------------------------------------------
    # 5. Replenishment Planning stage (unmodified agent, fed enhanced data)
    # ------------------------------------------------------------------
    print("\n--- 5. Replenishment Planning stage ---")
    replenishment = result["replenishment"]
    orders = replenishment["orders"]
    risky_count = sum(1 for a in assessments if a.risk_detected)
    check(
        "replenishment processed the risky items reported by monitoring",
        replenishment["risky_items_processed"] == risky_count,
    )
    for order in orders[:5]:
        check(f"order {order.order_id} has a positive order_quantity", order.order_quantity > 0)
        check(
            f"order {order.order_id} total_cost matches unit_cost * qty",
            abs(order.total_cost - order.unit_cost * order.order_quantity) < 0.01,
        )

    # ------------------------------------------------------------------
    # 6. Supplier Selection stage (unmodified agent, fed replenishment orders)
    # ------------------------------------------------------------------
    print("\n--- 6. Supplier Selection stage ---")
    supplier_selection = result["supplier_selection"]
    selections = supplier_selection["selections"]
    check(
        "supplier selection processed all replenishment orders",
        supplier_selection["orders_processed"] == len(orders),
    )
    check(
        "every order got exactly one selection",
        len(selections) == len(orders),
    )

    # ------------------------------------------------------------------
    # 7. No-Azure guarantee
    # ------------------------------------------------------------------
    print("\n--- 7. Runs correctly with Azure OFF ---")
    check("monitoring azure_analysis is None (Azure not configured)", monitoring.get("azure_analysis") is None)
    check("replenishment azure_analysis is None (Azure not configured)", replenishment.get("azure_analysis") is None)
    check(
        "supplier_selection azure_analysis is None (Azure not configured)",
        supplier_selection.get("azure_analysis") is None,
    )

    _summarize()


def _summarize():
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print("\n" + "=" * 60)
    print(f"FULL PIPELINE INTEGRATION TEST SUMMARY: {passed} passed, {failed} failed, {len(RESULTS)} total")
    print("=" * 60)
    if failed:
        print("\nFailed checks:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    run()

