import json
import os
import sys
from datetime import datetime
 
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
 
os.environ.setdefault("MODEL_PATH", "training_models/hybrid_model.pkl")
os.environ.setdefault("METRICS_PATH", "training_models/model_metrics.json")
# Kept small on purpose - this is a smoke/demo test, not a full batch run,
# and every risky row scored here also triggers an Azure call downstream.
# Raise this env var for a bigger demo (e.g. MAX_ML_FORECAST_CALLS=20).
os.environ.setdefault("MAX_ML_FORECAST_CALLS", "5")
 
CHECKS = []
 
 
def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    CHECKS.append((name, status, detail))
    icon = "\u2713" if status == "PASS" else "\u2717"
    line = f"  [{icon}] {name}"
    if detail and status == "FAIL":
        line += f" - {detail}"
    print(line)
    return condition
 
 
def money(x):
    try:
        return f"${x:,.2f}"
    except (TypeError, ValueError):
        return str(x)
 
 
def snippet(text, n=280):
    if not text:
        return "(none)"
    text = str(text).strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 3] + "..."
 
 
def section(title):
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)
 
 
def main():
    root = os.path.join(os.path.dirname(__file__), "..")
 
    model_path = os.path.join(root, os.environ["MODEL_PATH"])
    if not check(
        "trained model exists (run training_models/model_training.py first)",
        os.path.exists(model_path),
    ):
        return _finish(exit_early=True)
 
    from config import AzureOpenAIConfig
    try:
        AzureOpenAIConfig.from_env().validate()
        check("Azure config present in .env", True)
    except ValueError as e:
        check("Azure config present in .env", False, str(e))
        return _finish(exit_early=True)
 
    from orchestration.pipeline_orchestrator import PipelineOrchestrator
 
    print("\n" + "=" * 70)
    print("FULL PIPELINE - AZURE-ENABLED DEMO RUN")
    print("=" * 70)
    print(f"Started              : {datetime.now().isoformat(timespec='seconds')}")
    print(f"MAX_ML_FORECAST_CALLS: {os.environ['MAX_ML_FORECAST_CALLS']} "
          f"(raise this env var to score more rows)")
 
    try:
        orchestrator = PipelineOrchestrator(use_azure=True)
    except Exception as e:
        check("orchestrator initializes with use_azure=True", False, str(e))
        return _finish(exit_early=True)
    check("orchestrator initializes with use_azure=True", True)
 
    try:
        result = orchestrator.run()
    except Exception as e:
        check("pipeline.run() completes without raising", False, str(e))
        return _finish(exit_early=True)
    check("pipeline.run() completes without raising", True)
 
    # ------------------------------------------------------------------
    # [1/4] Inventory Monitoring
    # ------------------------------------------------------------------
    section("[1/4] INVENTORY MONITORING  (Phases 1-3)")
    monitoring = result["monitoring"]
    assessments = monitoring["assessments"]
    risky = [a for a in assessments if a.risk_detected]
 
    print(f"  Positions monitored   : {len(assessments):,}")
    print(f"  Risk detected on      : {len(risky):,} position(s)")
    print(f"  Local summary         : {snippet(monitoring.get('summary'), 200)}")
    print(f"  Azure analysis        : {snippet(monitoring.get('azure_analysis'))}")
    check("monitoring produced at least one assessment", len(assessments) > 0)
    check("monitoring azure_analysis is populated", bool(monitoring.get("azure_analysis")))
 
    # ------------------------------------------------------------------
    # [1b/4] Weather & Festival Context (Phase 6)
    # ------------------------------------------------------------------
    section("[1b/4] WEATHER & FESTIVAL CONTEXT  (Phase 6 enrichment)")
    weather_context_loaded = result.get("weather_context_loaded", 0)
    print(f"  Weather context entries loaded : {weather_context_loaded:,}")
 
    # Report assessments with weather context
    wx_enriched = [a for a in assessments if getattr(a, "weather_context", None) is not None]
    wx_high_risk = [a for a in wx_enriched if a.weather_context.is_high_risk()]
    wx_festival = [a for a in wx_enriched if a.weather_context.is_festival_day]
    print(f"  Assessments with weather context: {len(wx_enriched):,}")
    print(f"  High weather/festival risk       : {len(wx_high_risk):,}")
    print(f"  Active festival day positions    : {len(wx_festival):,}")
 
    # Top 3 weather-triggered risk reasons
    wx_reasons: list[str] = []
    for a in wx_high_risk[:5]:
        for r in a.risk_reasons:
            if any(kw in r.lower() for kw in ["weather", "festival", "extreme", "monsoon", "heat", "cold"]):
                if r not in wx_reasons:
                    wx_reasons.append(r)
    if wx_reasons:
        print("  Top weather/festival risk reasons:")
        for r in wx_reasons[:3]:
            print(f"    - {snippet(r, 120)}")
 
    check(
        "weather_context_loaded key present in pipeline result",
        "weather_context_loaded" in result,
    )
    check(
        "all assessments have weather_context attribute (None or WeatherFestivalContext)",
        all(hasattr(a, "weather_context") for a in assessments),
    )
 
    # ------------------------------------------------------------------
    # [2/4] Replenishment Planning
    # ------------------------------------------------------------------
    section("[2/4] REPLENISHMENT PLANNING  (Phase 4)")
    replenishment = result["replenishment"]
    orders = replenishment["orders"]
    r_summary = replenishment.get("summary")
 
    print(f"  Risky items processed : {replenishment.get('risky_items_processed', 0):,}")
    print(f"  Orders generated      : {len(orders):,}")
    if r_summary is not None:
        print(f"  Total order cost      : {money(r_summary.total_order_cost)}")
        print(f"  Orders by priority    : {r_summary.orders_by_priority}")
        print(f"  Average lead time     : {r_summary.average_lead_time:.1f} days")
    print(f"  Azure analysis        : {snippet(replenishment.get('azure_analysis'))}")
    check("replenishment generated orders for risky items", len(orders) > 0 or len(risky) == 0)
    check("replenishment azure_analysis is populated", bool(replenishment.get("azure_analysis")))
 
    # ------------------------------------------------------------------
    # [3/4] Supplier Selection
    # ------------------------------------------------------------------
    section("[3/4] SUPPLIER SELECTION  (Phase 5)")
    supplier_selection = result["supplier_selection"]
    selections = supplier_selection["selections"]
    s_summary = supplier_selection.get("summary")
 
    print(f"  Orders processed        : {supplier_selection.get('orders_processed', 0):,}")
    print(f"  Selections made         : {len(selections):,}")
    if s_summary is not None:
        print(f"  Total procurement cost  : {money(s_summary.total_procurement_cost)}")
        print(f"  Cost savings vs initial : {money(s_summary.cost_savings_vs_initial)}")
        print(f"  Policy compliant orders : {s_summary.policy_compliant_orders}/{s_summary.total_orders_selected}")
        print(f"  Unique suppliers used   : {s_summary.supplier_diversity}"
              + ("  <-- only 1 supplier won every order; see README assessment notes" if s_summary.supplier_diversity == 1 else ""))
    print(f"  Azure analysis          : {snippet(supplier_selection.get('azure_analysis'))}")
    check("supplier selection processed all orders", len(selections) == len(orders))
    check("supplier_selection azure_analysis is populated", bool(supplier_selection.get("azure_analysis")))
 
    # ------------------------------------------------------------------
    # [4/4] Demand Forecast Agent - shown LAST, on purpose
    # ------------------------------------------------------------------
    section("[4/4] DEMAND FORECAST AGENT  (Hybrid SARIMAX + XGBoost)")
    details = result.get("demand_forecast_details", [])
    succeeded = [d for d in details if d["status"] == "SUCCESS"]
    fallback = [d for d in details if d["status"] != "SUCCESS"]
    skipped_cap = result.get("demand_forecast_skipped_due_to_cap", 0)
 
    print(f"  Risky rows scored this run : {len(details)}  (of {len(risky)} total risky rows)")
    print(f"  ML forecast succeeded      : {len(succeeded)}")
    print(f"  Fell back to heuristic     : {len(fallback)}")
    if skipped_cap:
        print(f"  Skipped (over the cap)     : {skipped_cap}  "
              f"(raise MAX_ML_FORECAST_CALLS to score more)")
 
    if details:
        print()
        print(f"  {'SKU':<8}{'Loc':<6}{'Heuristic':<11}{'ML Forecast':<13}{'Confidence':<12}{'Status'}")
        print("  " + "-" * 66)
        for d in details:
            ml = f"{d['ml_forecasted_demand']:.1f}" if d["ml_forecasted_demand"] is not None else "-"
            conf = f"{d['confidence']:.1f}%" if d["confidence"] is not None else "-"
            print(
                f"  {d['sku_id']:<8}{d['location_id']:<6}"
                f"{d['heuristic_forecasted_demand']:<11}{ml:<13}{conf:<12}{d['status']}"
            )
        if fallback:
            print()
            print("  Fallback reason(s):")
            for d in fallback:
                print(f"    - SKU {d['sku_id']} @ Loc {d['location_id']}: {snippet(d['reason'], 160)}")
 
    check("demand forecast agent scored at least one risky row", len(details) > 0)
    check("at least one row got a real ML forecast (not just heuristic fallback)", len(succeeded) > 0)
 
    # ------------------------------------------------------------------
    # Save a COMPACT summary (never the full dataset - see README)
    # ------------------------------------------------------------------
    out_dir = os.path.join(root, "run_outputs")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"pipeline_summary_{ts}.json")
 
    compact = {
        "run_timestamp": ts,
        "azure_enabled": True,
        "inventory_monitoring": {
            "positions_monitored": len(assessments),
            "risky_positions_detected": len(risky),
            "summary": monitoring.get("summary"),
            "azure_analysis": monitoring.get("azure_analysis"),
        },
        "replenishment_planning": {
            "risky_items_processed": replenishment.get("risky_items_processed", 0),
            "orders_generated": len(orders),
            "total_order_cost": r_summary.total_order_cost if r_summary else None,
            "orders_by_priority": r_summary.orders_by_priority if r_summary else None,
            "top_5_orders": [str(o) for o in orders[:5]],
            "azure_analysis": replenishment.get("azure_analysis"),
        },
        "supplier_selection": {
            "orders_processed": supplier_selection.get("orders_processed", 0),
            "selections_made": len(selections),
            "total_procurement_cost": s_summary.total_procurement_cost if s_summary else None,
            "cost_savings_vs_initial": s_summary.cost_savings_vs_initial if s_summary else None,
            "supplier_diversity": s_summary.supplier_diversity if s_summary else None,
            "top_5_selections": [str(s) for s in selections[:5]],
            "azure_analysis": supplier_selection.get("azure_analysis"),
        },
        "demand_forecast_agent": {
            "rows_scored": len(details),
            "rows_succeeded": len(succeeded),
            "rows_fallback": len(fallback),
            "rows_skipped_due_to_cap": skipped_cap,
            "details": details,
        },
        "checks": [{"name": n, "status": s} for n, s, _ in CHECKS],
    }
    with open(out_path, "w") as f:
        json.dump(compact, f, indent=2, default=str)
    size_kb = os.path.getsize(out_path) / 1024
 
    return _finish(summary_path=out_path, summary_size_kb=size_kb)
 
 
def _finish(exit_early=False, summary_path=None, summary_size_kb=None):
    passed = sum(1 for _, s, _ in CHECKS if s == "PASS")
    failed = sum(1 for _, s, _ in CHECKS if s == "FAIL")
    print("\n" + "=" * 70)
    print(f"RESULT: {passed}/{len(CHECKS)} checks passed")
    if summary_path:
        print(f"Compact run summary saved to: {summary_path} ({summary_size_kb:.1f} KB)")
    if failed:
        print("\nFailed checks:")
        for name, status, detail in CHECKS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
    print("=" * 70)
    sys.exit(1 if failed or exit_early else 0)
 
 
if __name__ == "__main__":
    main()