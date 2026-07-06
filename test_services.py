import os
import sys
import traceback
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
TRAINING = ROOT / "training_models"

if str(TRAINING) not in sys.path:
    sys.path.insert(0, str(TRAINING))

import training_models.model_training

sys.modules["__main__"] = training_models.model_training


from demand_forecast_agent.agent import (
    DemandForecastAgent
)

from demand_forecast_agent.services.model_loader_service import (
    ModelLoaderService
)


# -------------------------
# LOAD INVENTORY STATE
# -------------------------

def load_inventory_payload(
    product_id
):

    inventory = pd.read_csv(

        ROOT
        /
        "csv_exports"
        /
        "db3_csv_export"
        /
        "inventory_positions.csv"

    )

    row = inventory[
        inventory["product_id"]
        ==
        product_id
    ]

    if row.empty:

        return None

    row = row.iloc[0]

    return {

        "product_id":

        int(
            row["product_id"]
        ),

        "location_id":

        int(
            row["location_id"]
        ),

        "on_hand_qty":

        float(
            row["on_hand_qty"]
        ),

        "safety_stock_qty":

        float(
            row["safety_stock_qty"]
        ),

        "reorder_point_qty":

        float(
            row["reorder_point_qty"]
        ),

        "allocated_qty":

        float(
            row["allocated_qty"]
        )

    }


# -------------------------
# TEST RUNNER
# -------------------------

def run_test():

    print("\n========== TEST START ==========\n")

    try:

        print("MODEL_PATH:")
        print(
            os.getenv(
                "MODEL_PATH"
            )
        )

        print("\n[1] Loading model...")

        model = (
            ModelLoaderService
            .load()
        )

        print(
            "\nPASS Model loaded"
        )

        print("\n===== MODEL =====")

        print(
            type(model)
        )

        print(
            "\nSARIMAX Weight:",
            model.sarimax_weight
        )

        print(
            "XGBoost Weight:",
            model.xgboost_weight
        )

        features = getattr(

            model.xgboost_model,

            "feature_cols",

            []

        )

        print(
            "\nFeatures:",
            len(features)
        )

        product_id = int(

            input(
                "\nEnter Product ID: "
            )

        )

        horizon = int(

            input(
                "Enter Forecast Horizon: "
            )

        )

        print(
            "\n[2] Fetching inventory state..."
        )

        payload = (

            load_inventory_payload(
                product_id
            )

        )

        if payload is None:

            print(
                "\nNO PRODUCT FOUND"
            )

            print(
                f"product_id={product_id}"
            )

            return

        print(
            "\nInventory Loaded:"
        )

        for k, v in payload.items():

            print(
                f"{k}: {v}"
            )

        print(
            "\n[3] Running Forecast Workflow..."
        )

        result = (

            DemandForecastAgent()

            .execute(

                payload,

                horizon

            )

        )

        print(
            "\n========== RESULT ==========\n"
        )

        if isinstance(
            result,
            dict
        ):

            for k, v in result.items():

                print(
                    f"{k}:"
                )

                print(v)

                print()

        else:

            print(
                result
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