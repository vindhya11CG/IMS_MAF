"""
Model training driver with segmented metrics and feature importance export.
"""
import json
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from training_models.hybrid_forecaster import HybridDemandForecaster


def main():
    print("=" * 70)
    print("DEMAND FORECASTING MODEL TRAINING")
    print("=" * 70)

    out_dir = os.path.dirname(__file__)

    print("\n[LOAD] Loading prepared data...")
    train_df = pd.read_pickle(os.path.join(out_dir, "train_data.pkl"))
    val_df = pd.read_pickle(os.path.join(out_dir, "val_data.pkl"))
    test_df = pd.read_pickle(os.path.join(out_dir, "test_data.pkl"))
    print(f"[OK] Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    model = HybridDemandForecaster()
    model.fit(train_df, val_df)

    test_results = model.evaluate(test_df)

    model.save(os.path.join(out_dir, "hybrid_model.pkl"))

    # Save metrics including segment-level results
    metrics_out = {
        "train_metrics": model.metrics.get("train", {}),
        "val_metrics": model.metrics.get("val", {}),
        "test_metrics": model.metrics.get("test", {}),
        "val_segment_metrics": model.metrics.get("val_segments", {}),
        "test_segment_metrics": model.metrics.get("test_segments", {}),
    }
    with open(os.path.join(out_dir, "model_metrics.json"), "w") as f:
        json.dump(metrics_out, f, indent=2, default=str)

    # Save feature list with importances
    importances = model.xgboost_model.feature_importances(top_n=len(model.xgboost_model.feature_cols))
    features_out = {
        "model_name": "Hybrid SARIMAX + XGBoost",
        "xgboost_features": model.xgboost_model.feature_cols,
        "feature_importances": {name: round(float(imp), 6) for name, imp in importances},
        "sarimax_weight": model.sarimax_weight,
        "xgboost_weight": model.xgboost_weight,
        "num_sarimax_models": len(model.sarimax_models),
        "feature_count": len(model.xgboost_model.feature_cols),
        "created_at": str(datetime.now()),
    }
    with open(os.path.join(out_dir, "model_features.json"), "w") as f:
        json.dump(features_out, f, indent=2)
    print("\n[OK] Features saved to model_features.json")
    print("[OK] Metrics saved to model_metrics.json")
    return model, test_results


if __name__ == "__main__":
    model, results = main()
