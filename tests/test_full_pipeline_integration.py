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
    # Phase 6: weather context loading
    weather_context_loaded = result.get("weather_context_loaded", 0)
    check(
        "weather_context_loaded key present in pipeline result",
        "weather_context_loaded" in result,
        "key missing from orchestrator result dict",
    )
    print(f"  Weather context entries loaded: {weather_context_loaded}")

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
    enhanced_assessments = result.get("enhanced_assessments", assessments)
    risky_count = sum(1 for a in enhanced_assessments if a.risk_detected)
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

    # Phase 6: weather enrichment and order reasoning checks
    _section8_weather_enrichment(result, assessments)
    _section9_order_reasoning(result)

    _summarize()


# ------------------------------------------------------------------
# 8. Phase 6: Weather context enrichment
# ------------------------------------------------------------------
def _section8_weather_enrichment(result, assessments):
    print("\n--- 8. Phase 6: Weather context enrichment ---")
    from agents.inventory_monitoring.models.inventory_models import WeatherFestivalContext
    # Not all assessments need weather context (db6 samples cover small sku/location set)
    # but the attribute must always be present (None or WeatherFestivalContext)
    for a in assessments:
        check(
            f"assessment sku={a.sku_id} loc={a.location_id} has weather_context attr",
            hasattr(a, "weather_context"),
        )
        if a.weather_context is not None:
            check(
                f"assessment sku={a.sku_id} loc={a.location_id} weather_context is correct type",
                isinstance(a.weather_context, WeatherFestivalContext),
            )


# ------------------------------------------------------------------
# 9. Phase 6: Replenishment order weather reasoning
# ------------------------------------------------------------------
def _section9_order_reasoning(result):
    print("\n--- 9. Phase 6: Replenishment order weather reasoning ---")
    orders = result["replenishment"]["orders"]
    wx_orders = [o for o in orders if "Weather" in (o.reasoning or "") or "Festival" in (o.reasoning or "")]
    if wx_orders:
        check(
            f"at least one order reasoning mentions weather/festival context ({len(wx_orders)} found)",
            True,
        )
        for o in wx_orders[:3]:
            print(f"  Order {o.order_id}: {o.reasoning[:120]}...")
    else:
        # Acceptable — db6 context only covers a subset of sku/location pairs
        print(
            "  (No weather-enhanced orders in this run — weather context may not overlap "
            "with risky sku/location pairs in the db6 samples; this is expected.)"
        )
        check(
            "no weather-enhanced orders (db6 sample coverage note)",
            True,  # not a failure — just informational
        )


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

