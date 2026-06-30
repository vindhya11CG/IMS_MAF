class InventoryDecisionService:

    def execute(
        self,
        forecast,
        stock
    ):

        if forecast > stock:
            return "REORDER_IMMEDIATELY"

        if forecast > stock * 0.8:
            return "MONITOR"

        return "SAFE"