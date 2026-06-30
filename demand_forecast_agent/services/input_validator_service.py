class InputValidatorService:

    def execute(
        self,
        payload,
        required_features
    ):

        missing = [
            f
            for f
            in required_features
            if f not in payload
        ]

        if missing:
            raise Exception(
                f"Missing features: {missing}"
            )

        for k, v in payload.items():

            if (
                isinstance(
                    v,
                    (
                        int,
                        float
                    )
                )
                and
                v < 0
            ):
                raise Exception(
                    f"{k} cannot be negative"
                )

        return True