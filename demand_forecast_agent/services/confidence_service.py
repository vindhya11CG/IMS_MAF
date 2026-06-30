import os
import json


class ConfidenceService:

    def execute(self):

        with open(
            os.getenv(
                "METRICS_PATH"
            )
        ) as f:

            metrics = json.load(
                f
            )

        return round(
            metrics[
                "test_metrics"
            ][
                "Accuracy_pct"
            ],
            2
        )