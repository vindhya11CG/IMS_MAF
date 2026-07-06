import json
import datetime


class LoggingService:

    def execute(

        self,

        payload

    ):

        ts = (

            datetime
            .datetime
            .now()
            .isoformat()

        )

        print("\n===== FORECAST LOG =====")

        print(ts)

        print(

            json.dumps(

                payload,

                indent=2,

                default=str

            )

        )

        print("========================")