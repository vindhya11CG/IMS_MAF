import pandas as pd

class BatchForecastService:

    def execute(
        self,
        model,
        rows,
        features,
        engineer
    ):

        df = pd.DataFrame(rows)

        df = engineer.execute(df)

        df = (
            df.reindex(
                columns=features,
                fill_value=0
            )
        )

        pred = model.predict(df)

        return [
            round(
                float(i),
                2
            )
            for i
            in pred
        ]