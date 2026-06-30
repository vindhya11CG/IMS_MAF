import sys
import joblib
import __main__

from training_models.model_training import (
    HybridDemandForecaster,
    SARIMAXModel,
    XGBoostModel,
)

# Register classes under __main__
__main__.HybridDemandForecaster = HybridDemandForecaster
__main__.SARIMAXModel = SARIMAXModel
__main__.XGBoostModel = XGBoostModel

MODEL = "training_models/hybrid_model.pkl"

print(f"Loading: {MODEL}")

model = joblib.load(MODEL)

print("\nSUCCESS")

print("\nTYPE:")
print(type(model))

print("\nMETRICS:")
print(model.metrics)

print("\nSARIMAX COUNT:")
print(len(model.sarimax_models))

print("\nWEIGHTS:")
print(model.sarimax_weight)
print(model.xgboost_weight)