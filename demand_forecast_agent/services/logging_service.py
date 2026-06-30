import datetime

class LoggingService:

    def execute(
        self,
        payload
    ):

        print("\n========== LOG ==========")

        print(
            datetime.datetime.now()
        )

        print(payload)

        print("=========================\n")