class ReorderService:

    def calculate_reorder(
        self,
        prediction,
        stock,
        safety=50
    ):

        qty = (
            prediction
            - stock
            + safety
        )

        return round(
            max(
                qty,
                0
            ),
            2
        )