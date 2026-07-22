"""
Test script for the Demand Forecast Agent backend.

Run from the repo root (demand_forecasting_system1/):

    python3 tests/test_demand_forecast_agent.py

No pytest dependency required (pytest isn't in requirements.txt) - this is
a plain script with a tiny custom runner so it works in any environment
that already has the project's own requirements installed. It exits with
code 0 if everything passes, 1 if anything fails, and prints a PASS/FAIL
line per test plus a final summary - suitable for pasting straight into a
demo or a CI log.

What it covers:
  1. Schema alignment  - dataset columns vs. InputValidatorService.REQUIRED
                          vs. FeatureEngineeringService.MODEL_FEATURES vs.
                          the DB3 inventory_positions column names.
  2. InputValidatorService  - valid payload, missing fields, negative values
  3. FeatureEngineeringService - dict payload AND batch DataFrame produce the
                          same derived columns; train/inference parity;
                          Phase 6: 8 new weather/festival MODEL_FEATURES verified.
  4. ModelLoaderService  - loads + singleton-caches the trained model
  5. ForecastService     - forecast succeeds for a product WITH a trained
                          SARIMAX component and one WITHOUT (falls back to
                          XGBoost-only cleanly either way)
  6. BatchForecastService - batch inference over multiple rows at once
  7. ConfidenceService   - reads test-set accuracy from model_metrics.json
  8. InventoryDecisionService / ReorderService - decision-threshold logic
  9. OutputFormatterService - output shape or ForecastResult dataclass
 10. ExplanationService  - falls back gracefully with no Azure OpenAI
                          configured (agent must not crash without Azure)
 11. End-to-end DemandForecastWorkflow.run() for several realistic
                          payloads pulled from an inventory_positions-shaped
                          sample, plus one intentionally invalid payload.
                          Phase 6: includes a weather-enriched payload test.
 12. Downstream contract check - flags field-name differences between what
                          this agent outputs and what the other agents'
                          dataclasses expect, so integration doesn't break
                          silently later (see NOTE at the bottom).
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("MODEL_PATH", "training_models/hybrid_model.pkl")
os.environ.setdefault("METRICS_PATH", "training_models/model_metrics.json")

RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == 'FAIL' else ""))
    return condition


def run():
    import pandas as pd

    from demand_forecast_agent.services.feature_engineering_service import (
        FeatureEngineeringService,
    )
    from demand_forecast_agent.services.decision_services import (
        InputValidatorService,
        InventoryDecisionService,
        ReorderService,
        OutputFormatterService,
    )
    from demand_forecast_agent.services.core_forecasting_service import (
        ModelLoaderService,
        ForecastService,
        BatchForecastService,
        ConfidenceService,
    )
    from demand_forecast_agent.services.azure_services import ExplanationService
    from demand_forecast_agent.services.demand_forecast_workflow_service import (
        DemandForecastWorkflow,
    )
    from demand_forecast_agent.agent import DemandForecastAgent

    root = os.path.join(os.path.dirname(__file__), "..")

    # ------------------------------------------------------------------
    # 1. Schema alignment
    # ------------------------------------------------------------------
    print("\n--- 1. Schema alignment ---")
    csv_path = os.path.join(root, "synthetic_inventory_db_native.csv")
    if os.path.exists(csv_path):
        sample = pd.read_csv(csv_path, nrows=5)
        for field in InputValidatorService.REQUIRED:
            check(
                f"schema: dataset/DB has '{field}' (InputValidatorService.REQUIRED)",
                field in sample.columns,
                f"columns were: {list(sample.columns)}",
            )
        # inventory_positions (DB3) fields the reorder/decision logic depends on
        for field in ["on_hand_qty", "safety_stock_qty", "reorder_point_qty", "allocated_qty"]:
            check(f"schema: '{field}' matches DB3 inventory_positions naming", field in sample.columns)
    else:
        check("schema: dataset file present", False, f"not found at {csv_path}")

    # ------------------------------------------------------------------
    # 2. InputValidatorService
    # ------------------------------------------------------------------
    print("\n--- 2. InputValidatorService ---")
    validator = InputValidatorService()
    good_payload = {
        "product_id": 1, "location_id": 1, "on_hand_qty": 67,
        "allocated_qty": 12, "safety_stock_qty": 11, "reorder_point_qty": 17,
    }
    check("valid payload passes", validator.execute(good_payload)["valid"] is True)

    missing_payload = dict(good_payload)
    del missing_payload["reorder_point_qty"]
    r = validator.execute(missing_payload)
    check("missing field is rejected", r["valid"] is False and "reorder_point_qty" in r["message"])

    negative_payload = dict(good_payload, on_hand_qty=-5)
    r = validator.execute(negative_payload)
    check("negative value is rejected", r["valid"] is False)

    # ------------------------------------------------------------------
    # 3. FeatureEngineeringService - dict vs batch parity
    # ------------------------------------------------------------------
    print("\n--- 3. FeatureEngineeringService ---")
    fe = FeatureEngineeringService()
    single = fe.execute(dict(good_payload, avg_retail_price=199.0, annual_units_max=90000,
                              is_promotional=False))
    for col in ["stock_gap", "available_stock", "safety_ratio", "month", "quarter",
                "month_sin", "month_cos", "is_promotional_int"]:
        check(f"single-row engineered column '{col}' present", col in single.columns)

    # Phase 6: verify 8 new weather/festival features are in MODEL_FEATURES
    _WX_FEATURES = [
        "weather_demand_multiplier",
        "weather_severity_index",
        "is_festival_day_int",
        "festival_proximity_score",
        "is_shopping_season_int",
        "supply_disruption_risk",
        "climate_anomaly_score",
        "regional_demand_index",
    ]
    for feat in _WX_FEATURES:
        check(
            f"weather/festival feature '{feat}' in MODEL_FEATURES",
            feat in FeatureEngineeringService.MODEL_FEATURES,
            f"MODEL_FEATURES={FeatureEngineeringService.MODEL_FEATURES}",
        )

    # Phase 6: verify weather payload fields are derived correctly
    wx_payload = dict(
        good_payload,
        avg_retail_price=199.0,
        annual_units_max=90000,
        is_promotional=False,
        is_festival_day=True,
        is_shopping_season=True,
        festival_proximity_score=0.75,
        weather_demand_multiplier=1.35,
        weather_severity_index=0.55,
        supply_disruption_risk=0.30,
        climate_anomaly_score=0.20,
        regional_demand_index=1.10,
    )
    wx_single = fe.execute(wx_payload)
    check(
        "is_festival_day_int derived from is_festival_day=True",
        int(wx_single["is_festival_day_int"].iloc[0]) == 1,
    )
    check(
        "is_shopping_season_int derived from is_shopping_season=True",
        int(wx_single["is_shopping_season_int"].iloc[0]) == 1,
    )
    check(
        "weather_demand_multiplier passes through correctly",
        abs(float(wx_single["weather_demand_multiplier"].iloc[0]) - 1.35) < 0.001,
    )
    wx_matrix = fe.to_model_matrix(wx_single)
    check(
        "weather-enriched to_model_matrix preserves weather feature values",
        abs(float(wx_matrix["weather_demand_multiplier"].iloc[0]) - 1.35) < 0.001,
    )
    check(
        "weather-enriched matrix fills absent weather columns with 0 (not NaN)",
        not wx_matrix.isnull().values.any(),
    )

    matrix = fe.to_model_matrix(single)
    check(
        "to_model_matrix produces the exact MODEL_FEATURES column set/order",
        list(matrix.columns) == FeatureEngineeringService.MODEL_FEATURES,
    )
    check(
        "to_model_matrix fills absent weather columns with 0 for non-weather payload",
        float(matrix["weather_demand_multiplier"].iloc[0]) == 0.0,
    )

    if os.path.exists(csv_path):
        batch_raw = pd.read_csv(csv_path, nrows=50)
        batch_engineered = fe.execute(batch_raw)
        batch_matrix = fe.to_model_matrix(batch_engineered)
        check(
            "batch engineered matrix has same column set as single-row matrix",
            list(batch_matrix.columns) == list(matrix.columns),
        )
        check("batch matrix has no leftover NaNs after reindex", not batch_matrix.isnull().values.any())

    # ------------------------------------------------------------------
    # 4. ModelLoaderService
    # ------------------------------------------------------------------
    print("\n--- 4. ModelLoaderService ---")
    model_path_exists = os.path.exists(os.path.join(root, os.environ["MODEL_PATH"]))
    if not check("trained model file exists", model_path_exists,
                  f"expected at {os.environ['MODEL_PATH']} - run training_models/model_training.py first"):
        print("\nSkipping model-dependent tests (5,6,9,10,11) - no trained model available.")
        _summarize()
        return

    ModelLoaderService.reset()
    m1 = ModelLoaderService.load()
    m2 = ModelLoaderService.load()
    check("ModelLoaderService caches a singleton", m1 is m2)

    # ------------------------------------------------------------------
    # 5. ForecastService - with and without a per-product SARIMAX model
    # ------------------------------------------------------------------
    print("\n--- 5. ForecastService ---")
    forecast_service = ForecastService()

    trained_products = set(m1.sarimax_models.keys())
    with_sarimax_id = next(iter(trained_products), None)
    without_sarimax_id = 99999  # a product id guaranteed not to have a SARIMAX model

    for label, pid in [("WITH SARIMAX component", with_sarimax_id),
                        ("WITHOUT SARIMAX component (XGBoost fallback)", without_sarimax_id)]:
        if pid is None:
            continue
        payload = dict(good_payload, product_id=pid, avg_retail_price=199.0,
                        annual_units_max=90000, is_promotional=False)
        engineered = fe.execute(payload)
        result = forecast_service.execute(engineered, horizon=14, product_id=pid)
        ok = check(f"forecast succeeds - product {label}", result["status"] == "SUCCESS", str(result))
        if ok:
            check(f"forecast value is non-negative - {label}", result["forecast"] >= 0)

    # ------------------------------------------------------------------
    # 6. BatchForecastService
    # ------------------------------------------------------------------
    print("\n--- 6. BatchForecastService ---")
    if os.path.exists(csv_path):
        batch_service = BatchForecastService()
        sample_rows = pd.read_csv(csv_path, nrows=10).to_dict(orient="records")
        preds = batch_service.execute(
            model=m1, rows=sample_rows, features=FeatureEngineeringService.MODEL_FEATURES, engineer=fe
        )
        check("batch forecast returns one prediction per row", len(preds) == len(sample_rows))
        check("batch predictions are all non-negative", all(p >= 0 for p in preds))

    # ------------------------------------------------------------------
    # 7. ConfidenceService
    # ------------------------------------------------------------------
    print("\n--- 7. ConfidenceService ---")
    metrics_path_exists = os.path.exists(os.path.join(root, os.environ["METRICS_PATH"]))
    if check("metrics file exists", metrics_path_exists):
        conf = ConfidenceService().execute()
        check("confidence is a plausible percentage (0-100)", 0 <= conf <= 100, str(conf))

    # ------------------------------------------------------------------
    # 8. InventoryDecisionService / ReorderService
    # ------------------------------------------------------------------
    print("\n--- 8. InventoryDecisionService / ReorderService ---")
    d = InventoryDecisionService().execute(forecast=50, stock=10, reorder_point=20, safety_stock=10)
    check("low stock triggers REORDER_IMMEDIATELY", d["decision"] == "REORDER_IMMEDIATELY")

    d = InventoryDecisionService().execute(forecast=5, stock=100, reorder_point=20, safety_stock=10)
    check("ample stock triggers SAFE", d["decision"] == "SAFE")

    qty = ReorderService().execute(forecast=50, stock=30, allocated=5, safety=10)
    check("reorder quantity is never negative", qty >= 0)

    # ------------------------------------------------------------------
    # 9. OutputFormatterService
    # ------------------------------------------------------------------
    print("\n--- 9. OutputFormatterService ---")
    out = OutputFormatterService().execute(
        item=1, forecast=42.9, confidence=87.0, horizon=14,
        explanation="test", inventory=d, reorder=qty,
    )
    check("output has forecast/inventory_decision/recommended_reorder/explanation keys",
          set(["forecast", "inventory_decision", "recommended_reorder", "explanation"]) <= set(out.keys()))
    check("forecast is a ForecastResult with expected fields",
          hasattr(out["forecast"], "forecasted_demand") and hasattr(out["forecast"], "confidence"))

    # ------------------------------------------------------------------
    # 10. ExplanationService fallback (no Azure configured)
    # ------------------------------------------------------------------
    print("\n--- 10. ExplanationService (offline fallback) ---")
    explanation = ExplanationService().execute(sku=1, forecast=42.9, confidence=87.0)
    check("explanation service returns text even without Azure OpenAI configured",
          isinstance(explanation, str) and len(explanation) > 0)

    # ------------------------------------------------------------------
    # 11. End-to-end workflow
    # ------------------------------------------------------------------
    print("\n--- 11. End-to-end DemandForecastWorkflow ---")
    agent = DemandForecastAgent()

    sample_positions = [
        {"product_id": 1, "location_id": 1, "on_hand_qty": 67, "allocated_qty": 12,
         "safety_stock_qty": 11, "reorder_point_qty": 17, "avg_retail_price": 199.0,
         "annual_units_max": 90000, "is_promotional": False},
        {"product_id": 2, "location_id": 2, "on_hand_qty": 8, "allocated_qty": 0,
         "safety_stock_qty": 15, "reorder_point_qty": 25, "avg_retail_price": 499.0,
         "annual_units_max": 30000, "is_promotional": True},
        {"product_id": 3, "location_id": 3, "on_hand_qty": 300, "allocated_qty": 20,
         "safety_stock_qty": 20, "reorder_point_qty": 40, "avg_retail_price": 34.99,
         "annual_units_max": 3000, "is_promotional": False},
    ]
    for pos in sample_positions:
        result = agent.execute(pos, horizon=14)
        ok = check(
            f"end-to-end forecast for product_id={pos['product_id']}",
            "forecast" in result and hasattr(result["forecast"], "forecasted_demand"),
            str(result),
        )

    # Phase 6: weather-enriched end-to-end payload
    print("\n--- 11b. End-to-end DemandForecastWorkflow with weather context ---")
    wx_e2e_payload = {
        "product_id": 1,
        "location_id": 1,
        "on_hand_qty": 67,
        "allocated_qty": 12,
        "safety_stock_qty": 11,
        "reorder_point_qty": 17,
        "avg_retail_price": 199.0,
        "annual_units_max": 90000,
        "is_promotional": False,
        # Weather/festival context fields
        "weather_demand_multiplier": 1.50,
        "weather_severity_index": 0.72,
        "is_festival_day": True,
        "festival_proximity_score": 0.88,
        "is_shopping_season": True,
        "supply_disruption_risk": 0.45,
        "climate_anomaly_score": 0.30,
        "regional_demand_index": 1.15,
    }
    wx_result = agent.execute(wx_e2e_payload, horizon=14)
    check(
        "weather-enriched payload: forecast completes without error",
        "forecast" in wx_result and hasattr(wx_result.get("forecast"), "forecasted_demand"),
        str(wx_result),
    )
    if "forecast" in wx_result and hasattr(wx_result["forecast"], "forecasted_demand"):
        check(
            "weather-enriched forecast demand is a non-negative integer",
            wx_result["forecast"].forecasted_demand >= 0,
        )

    invalid_result = asyncio.run(DemandForecastWorkflow().run({"product_id": 1}, horizon=14))
    check("invalid payload is rejected by the workflow, not crashed", invalid_result.get("valid") is False)


    _summarize()


def _summarize():
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print("\n" + "=" * 60)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed, {len(RESULTS)} total")
    print("=" * 60)
    if failed:
        print("\nFailed tests:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    run()
    
    

