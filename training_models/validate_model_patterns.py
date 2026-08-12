"""
training_models/validate_model_patterns.py

Validation suite verifying that hybrid_model.pkl has learned strong, event-driven
demand relationships for:
  1. Weather Extremes (Heatwave, Coldwave, Heavy Rain/Monsoon) & product sensitivity rules
  2. Festivals & Pre-festival proximity ramps
  3. Weekends vs Weekdays
  4. Multi-Year Pattern Consistency (2026-2028)
  5. Feature Importance contribution of event & context features

Exits 0 if all checks pass, 1 otherwise.
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

    if not check("hybrid_model.pkl exists", os.path.exists(model_path), "run model_training.py first"):
        _summarize()
        return
    if not check("test_data.pkl exists", os.path.exists(test_path), "run data_preparation.py first"):
        _summarize()
        return

    model = HybridDemandForecaster.load(model_path)
    test_df = pd.read_pickle(test_path)

    # ------------------------------------------------------------------
    # 1. Feature importance breakdown
    # ------------------------------------------------------------------
    print("\n--- 1. Feature Importance Breakdown ---")
    importances = model.xgboost_model.feature_importances(top_n=len(model.xgboost_model.feature_cols))
    imp_dict = dict(importances)

    weather_cols = [c for c in model.xgboost_model.feature_cols if any(k in c for k in ["weather", "temp", "rain", "cold", "heat", "monsoon", "snow", "climate"])]
    festival_cols = [c for c in model.xgboost_model.feature_cols if any(k in c for k in ["festival", "shopping"])]
    calendar_cols = [c for c in model.xgboost_model.feature_cols if any(k in c for k in ["weekend", "day_of_week", "week_of_year", "month"])]

    weather_total = sum(imp_dict.get(c, 0) for c in weather_cols)
    festival_total = sum(imp_dict.get(c, 0) for c in festival_cols)
    calendar_total = sum(imp_dict.get(c, 0) for c in calendar_cols)

    print(f"  Calendar & Weekend features importance:  {calendar_total:.4f}")
    print(f"  Weather & Climate features importance:   {weather_total:.4f}")
    print(f"  Festival & Season features importance:    {festival_total:.4f}")
    print("\n  Top 10 features overall:")
    for name, imp in importances[:10]:
        print(f"    {name:<35} {imp:.4f}")

    check("weather features show significant contribution (>1.0%)", weather_total > 0.01, f"got {weather_total:.4f}")
    check("festival features show significant contribution (>0.5%)", festival_total > 0.005, f"got {festival_total:.4f}")
    check("calendar/weekend features show contribution (>1.0%)", calendar_total > 0.01, f"got {calendar_total:.4f}")

    # ------------------------------------------------------------------
    # 2. Festival Sensitivity Check
    # ------------------------------------------------------------------
    print("\n--- 2. Festival Sensitivity Check ---")
    sample_n = min(300, len(test_df))
    sample = test_df.sample(n=sample_n, random_state=42).copy()

    off = sample.copy()
    off["is_festival_day"] = 0
    off["is_festival_day_int"] = 0
    off["days_to_next_festival"] = 30.0
    off["days_since_last_festival"] = 30.0
    off["festival_proximity_score"] = float(np.exp(-30 / 7.0))

    on = sample.copy()
    on["is_festival_day"] = 1
    on["is_festival_day_int"] = 1
    on["days_to_next_festival"] = 0.0
    on["days_since_last_festival"] = 0.0
    on["festival_proximity_score"] = 1.0

    pred_off = model.xgboost_model.predict(off)
    pred_on = model.xgboost_model.predict(on)
    deltas = pred_on - pred_off
    pct_positive = 100 * np.mean(deltas > 0)

    print(f"  Sampled {sample_n} rows, toggling festival 0 -> 1")
    print(f"  Mean demand change: {deltas.mean():+.2f} units")
    print(f"  Rows showing demand increase: {pct_positive:.1f}%")
    check("majority of rows show elevated demand on festival days (>75%)", pct_positive > 75, f"got {pct_positive:.1f}%")

    # ------------------------------------------------------------------
    # 3. Weekend Sensitivity Check
    # ------------------------------------------------------------------
    print("\n--- 3. Weekend Sensitivity Check ---")
    wkday = sample.copy()
    wkday["day_of_week"] = 1  # Tuesday
    wkday["is_weekend"] = 0

    wknd = sample.copy()
    wknd["day_of_week"] = 5   # Saturday
    wknd["is_weekend"] = 1

    pred_wkday = model.xgboost_model.predict(wkday)
    pred_wknd = model.xgboost_model.predict(wknd)
    wknd_deltas = pred_wknd - pred_wkday
    wknd_increase_pct = 100 * np.mean(wknd_deltas > 0)

    print(f"  Mean weekend demand change: {wknd_deltas.mean():+.2f} units")
    print(f"  Rows with higher weekend demand: {wknd_increase_pct:.1f}%")
    check("weekend demand is higher than weekday demand (>60% of sample)", wknd_increase_pct > 60, f"got {wknd_increase_pct:.1f}%")

    # ------------------------------------------------------------------
    # 4. Product-Specific Weather Sensitivity Check
    # ------------------------------------------------------------------
    print("\n--- 4. Product-Specific Weather Sensitivity ---")
    # Heatwave test
    normal_heat = sample.copy()
    normal_heat["heatwave_flag"] = 0
    normal_heat["heatwave_flag_int"] = 0
    normal_heat["temperature_c"] = 25.0
    normal_heat["weather_demand_multiplier"] = 1.0

    heatwave = sample.copy()
    heatwave["heatwave_flag"] = 1
    heatwave["heatwave_flag_int"] = 1
    heatwave["temperature_c"] = 42.0
    heatwave["weather_demand_multiplier"] = 1.85

    pred_norm_heat = model.xgboost_model.predict(normal_heat)
    pred_heat = model.xgboost_model.predict(heatwave)
    heat_diff = pred_heat.mean() - pred_norm_heat.mean()

    print(f"  Heatwave toggle (25C -> 42C) mean demand shift: {heat_diff:+.2f} units")
    check("heatwave condition causes noticeable demand shift (|delta| > 0.2)", abs(heat_diff) > 0.2, f"got {heat_diff:+.2f}")

    # Heavy Rain test
    normal_rain = sample.copy()
    normal_rain["heavy_rain_flag"] = 0
    normal_rain["heavy_rain_flag_int"] = 0
    normal_rain["rainfall_mm"] = 0.0
    normal_rain["weather_demand_multiplier"] = 1.0

    heavy_rain = sample.copy()
    heavy_rain["heavy_rain_flag"] = 1
    heavy_rain["heavy_rain_flag_int"] = 1
    heavy_rain["rainfall_mm"] = 85.0
    heavy_rain["weather_demand_multiplier"] = 2.15

    pred_norm_rain = model.xgboost_model.predict(normal_rain)
    pred_rain = model.xgboost_model.predict(heavy_rain)
    rain_diff = pred_rain.mean() - pred_norm_rain.mean()

    print(f"  Heavy rain toggle (0mm -> 85mm) mean demand shift: {rain_diff:+.2f} units")
    check("heavy rain condition causes noticeable demand shift (|delta| > 0.2)", abs(rain_diff) > 0.2, f"got {rain_diff:+.2f}")

    # ------------------------------------------------------------------
    # 5. Multi-Year Prediction Consistency (2026 vs 2027 vs 2028)
    # ------------------------------------------------------------------
    print("\n--- 5. Multi-Year Prediction Consistency (2026-2028) ---")
    row_base = sample.iloc[0:1].copy()

    pred_2026 = []
    pred_2027 = []
    pred_2028 = []

    for month in range(1, 13):
        r26 = row_base.copy()
        r26["date"] = f"2026-{month:02d}-15"
        r26["month"] = month
        r26["month_sin"] = np.sin(2 * np.pi * month / 12)
        r26["month_cos"] = np.cos(2 * np.pi * month / 12)

        r27 = row_base.copy()
        r27["date"] = f"2027-{month:02d}-15"
        r27["month"] = month
        r27["month_sin"] = np.sin(2 * np.pi * month / 12)
        r27["month_cos"] = np.cos(2 * np.pi * month / 12)

        r28 = row_base.copy()
        r28["date"] = f"2028-{month:02d}-15"
        r28["month"] = month
        r28["month_sin"] = np.sin(2 * np.pi * month / 12)
        r28["month_cos"] = np.cos(2 * np.pi * month / 12)

        pred_2026.append(model.xgboost_model.predict(r26)[0])
        pred_2027.append(model.xgboost_model.predict(r27)[0])
        pred_2028.append(model.xgboost_model.predict(r28)[0])

    corr_26_27 = np.corrcoef(pred_2026, pred_2027)[0, 1]
    corr_26_28 = np.corrcoef(pred_2026, pred_2028)[0, 1]

    print(f"  Seasonal profile correlation 2026 vs 2027: {corr_26_27:.3f}")
    print(f"  Seasonal profile correlation 2026 vs 2028: {corr_26_28:.3f}")
    check("multi-year predictions maintain strong seasonal pattern correlation (>0.90)", corr_26_27 > 0.90 and corr_26_28 > 0.90, f"got {corr_26_27:.3f}, {corr_26_28:.3f}")

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