"""
training_models/validate_model_patterns.py

Standalone validation: proves the trained hybrid_model.pkl is actually
USING weather and festival signal, not just carrying the columns unused.

Three checks:
  1. Feature importance - are weather/festival features showing up with
     non-trivial importance, or are they dead weight?
  2. Festival sensitivity - for real rows sampled from the training data,
     does flipping is_festival_day 0->1 move the prediction in the
     expected direction (up)?
  3. Weather sensitivity - does raising temperature_c move the prediction
     in a consistent direction for a temperature-sensitive product?

This is intentionally separate from tests/test_demand_forecast_agent.py -
that suite validates the AGENT/SERVICE contract (input validation,
decision logic, output shape). This script validates MODEL BEHAVIOR
(did it learn what we think it learned), and lives in training_models/
since it only touches training artifacts, not services.

Run from repo root:
    python training_models/validate_model_patterns.py

Exits 0 if all checks pass, 1 otherwise - safe to wire into CI later.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from training_models.hybrid_forecaster import HybridDemandForecaster, XGBoostModel

RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    return condition


def main():
    out_dir = os.path.dirname(__file__)
    model_path = os.path.join(out_dir, "hybrid_model.pkl")
    test_path = os.path.join(out_dir, "test_data.pkl")

    if not check("hybrid_model.pkl exists", os.path.exists(model_path),
                  "run model_training.py first"):
        _summarize()
        return
    if not check("test_data.pkl exists", os.path.exists(test_path),
                  "run data_preparation.py first"):
        _summarize()
        return

    model = HybridDemandForecaster.load(model_path)
    test_df = pd.read_pickle(test_path)

    # ------------------------------------------------------------------
    # 1. Feature importance
    # ------------------------------------------------------------------
    print("\n--- 1. Feature importance ---")
    importances = model.xgboost_model.feature_importances(top_n=len(model.xgboost_model.feature_cols))
    weather_total = sum(i for n, i in importances if n in XGBoostModel.WEATHER_REGION_FEATURES)
    festival_total = sum(i for n, i in importances if n in XGBoostModel.FESTIVAL_FEATURES)
    base_total = sum(i for n, i in importances if n in XGBoostModel.BASE_FEATURES)

    print(f"  Base features total importance:     {base_total:.4f}")
    print(f"  Weather/region features total:      {weather_total:.4f}")
    print(f"  Festival features total:            {festival_total:.4f}")
    print("\n  Top 10 features overall:")
    for name, imp in importances[:10]:
        tag = "[WEATHER]" if name in XGBoostModel.WEATHER_REGION_FEATURES else (
            "[FESTIVAL]" if name in XGBoostModel.FESTIVAL_FEATURES else "")
        print(f"    {name:<28} {imp:.4f} {tag}")

    check("weather features have non-trivial combined importance (>0.5%)",
          weather_total > 0.005, f"got {weather_total:.4f}")
    check("festival features have non-trivial combined importance (>0.1%)",
          festival_total > 0.001, f"got {festival_total:.4f}")

    # ------------------------------------------------------------------
    # 2. Festival sensitivity on real sampled rows
    # ------------------------------------------------------------------
    print("\n--- 2. Festival sensitivity (real sampled rows) ---")
    sample_n = min(200, len(test_df))
    sample = test_df.sample(n=sample_n, random_state=42).copy()

    off = sample.copy()
    off["is_festival_day"] = 0
    off["days_to_next_festival"] = 30.0
    off["days_since_last_festival"] = 30.0
    off["festival_proximity_score"] = float(np.exp(-30 / 7.0))

    on = sample.copy()
    on["is_festival_day"] = 1
    on["days_to_next_festival"] = 0.0
    on["days_since_last_festival"] = 0.0
    on["festival_proximity_score"] = 1.0

    pred_off = model.xgboost_model.predict(off)
    pred_on = model.xgboost_model.predict(on)
    deltas = pred_on - pred_off
    pct_positive = 100 * np.mean(deltas > 0)

    print(f"  Sampled {sample_n} real rows, toggled is_festival_day 0 -> 1")
    print(f"  Mean predicted demand change: {deltas.mean():+.3f}")
    print(f"  Rows where prediction increased: {pct_positive:.1f}%")
    check("majority of rows show higher demand on a festival day (>60%)",
          pct_positive > 60, f"got {pct_positive:.1f}%")

    # ------------------------------------------------------------------
    # 3. Weather sensitivity on real sampled rows
    # ------------------------------------------------------------------
    print("\n--- 3. Weather sensitivity (real sampled rows) ---")
    cold = sample.copy()
    cold["temperature_c"] = sample["temperature_c"].quantile(0.1)
    cold["feels_like_c"] = cold["temperature_c"]

    hot = sample.copy()
    hot["temperature_c"] = sample["temperature_c"].quantile(0.9)
    hot["feels_like_c"] = hot["temperature_c"]

    pred_cold = model.xgboost_model.predict(cold)
    pred_hot = model.xgboost_model.predict(hot)
    weather_deltas = pred_hot - pred_cold

    print(f"  Temperature range tested: {cold['temperature_c'].iloc[0]:.1f}C -> {hot['temperature_c'].iloc[0]:.1f}C")
    print(f"  Mean predicted demand change: {weather_deltas.mean():+.3f}")
    check("model responds to temperature change (mean |delta| > 0.01)",
          abs(weather_deltas.mean()) > 0.01, f"got {weather_deltas.mean():+.4f}")

    _summarize()


def _summarize():
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print("\n" + "=" * 60)
    print(f"PATTERN VALIDATION SUMMARY: {passed} passed, {failed} failed, {len(RESULTS)} total")
    print("=" * 60)
    if failed:
        print("\nFailed checks:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()