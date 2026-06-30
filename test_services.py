import os
import traceback
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
TRAINING = ROOT / "training_models"

if str(TRAINING) not in sys.path:
    sys.path.insert(0, str(TRAINING))

import training_models.model_training

sys.modules["__main__"] = training_models.model_training


from demand_forecast_agent.services.model_loader_service import (
    ModelLoaderService
)

from demand_forecast_agent.services.forecast_service import (
    ForecastService
)

from demand_forecast_agent.services.confidence_service import (
    ConfidenceService
)

from demand_forecast_agent.services.output_formatter_service import (
    OutputFormatterService
)

from demand_forecast_agent.services.inventory_decision_service import (
    InventoryDecisionService
)

from demand_forecast_agent.services.reorder_service import (
    ReorderService
)

from demand_forecast_agent.services.logging_service import (
    LoggingService
)

from demand_forecast_agent.services.feature_engineering_service import (
    FeatureEngineeringService
)


# -------------------------
# MOCK EXPLANATION
# -------------------------

class MockExplanationService:

    def execute(
        self,
        sku,
        forecast,
        confidence
    ):

        return f"""
Local test completed.

SKU: {sku}
Forecast: {round(forecast,2)}
Confidence: {confidence}%

(No Azure explanation)
"""


# -------------------------
# TEST RUNNER
# -------------------------

def run_test():

    print("\n========== TEST START ==========\n")

    try:

        print("MODEL_PATH:")
        print(os.getenv("MODEL_PATH"))

        print("\nDATA_PATH:")
        print(os.getenv("DATA_PATH"))

        print("\nMETRICS_PATH:")
        print(os.getenv("METRICS_PATH"))

        # --------------------------------
        # LOAD MODEL
        # --------------------------------

        print("\n[1] Loading model...")

        model = (
            ModelLoaderService
            .load()
        )

        print("\nPASS Model loaded")

        print("\n===== MODEL DETAILS =====")

        print("Model Type:")
        print(type(model))

        print("\nWeights:")
        print("SARIMAX:", model.sarimax_weight)
        print("XGBoost:", model.xgboost_weight)

        # --------------------------------
        # FEATURES
        # --------------------------------

        features = getattr(
            model.xgboost_model,
            "feature_cols",
            []
        )

        print("\n===== MODEL FEATURES =====")

        print(
            f"Total Features: {len(features)}"
        )

        for i, f in enumerate(
            features,
            start=1
        ):
            print(f"{i}. {f}")

        # --------------------------------
        # SARIMAX
        # --------------------------------

        print("\n===== SARIMAX DETAILS =====")

        print(
            "Loaded Models:",
            len(
                model.sarimax_models
            )
        )

        if model.sarimax_models:

            print(
                "\nSample Items:"
            )

            for item in (
                list(
                    model
                    .sarimax_models
                    .keys()
                )[:10]
            ):
                print("-", item)

        # --------------------------------
        # METRICS
        # --------------------------------

        print(
            "\n===== TRAINING METRICS ====="
        )

        for phase, vals in (
            model.metrics.items()
        ):

            print(
                f"\n{phase.upper()}"
            )

            for k, v in (
                vals.items()
            ):
                print(
                    f"{k}: {v}"
                )

        # --------------------------------
        # USER INPUT
        # --------------------------------

        item = input(
            "\nEnter item_id: "
        )

        horizon = int(
            input(
                "Forecast horizon: "
            )
        )

        stock_level = float(
            input(
                "Current stock level: "
            )
        )

        # --------------------------------
        # FORECAST
        # --------------------------------

        print(
            "\n[2] Forecasting..."
        )

        response = (
            ForecastService()
            .execute(
                item,
                horizon
            )
        )
        if response["status"] == "NO_ITEM_FOUND":
            print("\n========== RESULT ==========\n")
            print(response["message"])
            print(
                "\nPASS END-TO-END SUCCESS"
            )
            return
        forecast = response["forecast"]
        print(
            f"PASS Forecast = {forecast}"
        )

        # --------------------------------
        # CONFIDENCE
        # --------------------------------

        print(
            "\n[3] Loading confidence..."
        )

        confidence = (
            ConfidenceService()
            .execute()
        )

        print(
            f"PASS Confidence = {confidence}%"
        )

        # --------------------------------
        # INVENTORY
        # --------------------------------

        print(
            "\n[4] Inventory Decision..."
        )

        decision = (
            InventoryDecisionService()
            .execute(
                forecast,
                stock_level
            )
        )

        reorder = (
            ReorderService()
            .calculate_reorder(
                forecast,
                stock_level
            )
        )

        print(
            "Decision:",
            decision
        )

        print(
            "Reorder Qty:",
            reorder
        )

        # --------------------------------
        # LOGGING
        # --------------------------------

        print(
            "\n[5] Logging..."
        )

        LoggingService.execute(
            {
                "item_id": item,
                "stock_level": stock_level
            },
            forecast
        )

        # --------------------------------
        # EXPLANATION
        # --------------------------------

        print(
            "\n[6] Explanation..."
        )

        explanation = (
            MockExplanationService()
            .execute(
                item,
                forecast,
                confidence
            )
        )

        print(
            "PASS Explanation generated"
        )

        # --------------------------------
        # FORMAT
        # --------------------------------

        print(
            "\n[7] Formatting..."
        )

        result = (
            OutputFormatterService()
            .execute(
                item,
                forecast,
                confidence,
                horizon,
                explanation
            )
        )

        print(
            "\n========== RESULT ==========\n"
        )

        print(
            result[0]
        )

        print(
            "\nExplanation:"
        )

        print(
            result[1]
        )

        print(
            "\nInventory Decision:"
        )

        print(
            decision
        )

        print(
            "\nRecommended Reorder:"
        )

        print(
            reorder
        )

        print(
            "\nPASS END-TO-END SUCCESS"
        )

    except Exception:

        print(
            "\nFAILED\n"
        )

        traceback.print_exc()


if __name__ == "__main__":

    run_test()
