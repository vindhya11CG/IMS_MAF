"""
Model training driver.

FIX (this pass): the SARIMAXModel / XGBoostModel / HybridDemandForecaster
classes used to be defined directly in this file. Running this file as a
script makes Python treat it as the `__main__` module, so joblib pickled
HybridDemandForecaster with the module reference `__main__` - which breaks
the moment anything OTHER than this exact script (tests, the live agent,
etc.) tries to unpickle it:

    AttributeError: Can't get attribute 'HybridDemandForecaster' on
    <module '__main__' from '...test_demand_forecast_agent.py'>

The classes now live in `training_models/hybrid_forecaster.py`, a module
that's always imported by its real dotted path and never run directly as
`__main__`. This file only drives the pipeline: load prepared data, fit,
evaluate, save. No modeling logic changed.

IMPORTANT: any hybrid_model.pkl saved before this fix is still broken -
delete it and rerun this script to regenerate a working one. See the
integration guide.
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
    print(f"\u2713 Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    model = HybridDemandForecaster()
    model.fit(train_df, val_df)

    test_results = model.evaluate(test_df)

    model.save(os.path.join(out_dir, "hybrid_model.pkl"))

    with open(os.path.join(out_dir, "model_metrics.json"), "w") as f:
        json.dump(
            {
                "train_metrics": model.metrics.get("train", {}),
                "val_metrics": model.metrics.get("val", {}),
                "test_metrics": model.metrics.get("test", {}),
            },
            f,
            indent=2,
            default=str,
        )

    with open(os.path.join(out_dir, "model_features.json"), "w") as f:
        json.dump(
            {
                "model_name": "Hybrid SARIMAX + XGBoost",
                "xgboost_features": model.xgboost_model.feature_cols,
                "sarimax_weight": model.sarimax_weight,
                "xgboost_weight": model.xgboost_weight,
                "num_sarimax_models": len(model.sarimax_models),
                "feature_count": len(model.xgboost_model.feature_cols),
                "created_at": str(datetime.now()),
            },
            f,
            indent=2,
        )
    print("\n\u2713 Features saved to model_features.json")
    print("\u2713 Metrics saved to model_metrics.json")
    return model, test_results


if __name__ == "__main__":
    model, results = main()
