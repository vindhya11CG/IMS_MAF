from agents.replenishment_planning.services.supplier_matching_service import SupplierMatchingService


class DummyLoader:
    def __init__(self):
        self._suppliers = [
            {"supplier_id": 1, "supplier_name": "Global Tech Supplies", "lead_time_days": 7, "minimum_order_qty": 1},
        ]
        self._pricing_tiers = []
        self._category_mappings = [
            {"supplier_id": 1, "category_id": 10, "unit_cost": 35.0},
        ]
        self._products = [
            {"sku_id": 101, "category_id": 10},
            {"sku_id": 102, "category_id": 10},
        ]
        self._performance_metrics = [
            {"supplier_id": 1, "on_time_delivery_rate": 0.95, "quality_score": 0.92},
        ]
        self._product_overrides = [
            {"supplier_id": 1, "sku_id": 101, "unit_cost": 54.95},
        ]

    def load_suppliers(self):
        return self._suppliers

    def load_supplier_pricing_tiers(self):
        return self._pricing_tiers

    def load_supplier_category_mapping(self):
        return self._category_mappings

    def load_products(self):
        return self._products

    def load_supplier_performance_metrics(self):
        return self._performance_metrics

    def load_supplier_product_overrides(self):
        return self._product_overrides


def test_supplier_product_override_takes_priority_for_global_tech_supplies():
    service = SupplierMatchingService(loader=DummyLoader())

    assert service._get_unit_cost(1, 101, 10) == 54.95
    assert service._get_unit_cost(1, 102, 10) == 35.0
