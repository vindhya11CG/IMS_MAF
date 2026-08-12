#!/usr/bin/env python3
import csv
import json
import urllib.request
from decimal import Decimal
from pathlib import Path

BASE_URL = "http://127.0.0.1:8888/api/v1"
ROOT = Path(__file__).resolve().parents[1]
CSV_ROOT = ROOT / "data" / "csv_exports"


def read_csv_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [row for row in reader if row]


def load_products():
    products = {}
    for row in read_csv_rows(CSV_ROOT / "db2_csv_export" / "products.csv"):
        sku = row.get("sku_id") or row.get("product_id")
        if sku:
            products[int(sku)] = {
                "product_name": row.get("product_name", "").strip(),
                "category_id": int(row.get("category_id", 0) or 0),
            }
    return products


def load_supplier_product_overrides():
    overrides = {}
    path = CSV_ROOT / "db4_csv_export" / "supplier_product_pricing.csv"
    if not path.exists():
        return overrides
    for row in read_csv_rows(path):
        sid = int(row.get("supplier_id", 0) or 0)
        sku = int(row.get("sku_id", 0) or 0)
        cost = Decimal(str(row.get("unit_cost", "0") or "0"))
        if sid and sku:
            overrides[(sid, sku)] = cost
    return overrides


def load_supplier_category_mapping():
    mapping = {}
    path = CSV_ROOT / "db4_csv_export" / "supplier_category_mapping.csv"
    for row in read_csv_rows(path):
        sid = int(row.get("supplier_id", 0) or 0)
        cat = int(row.get("category_id", 0) or 0)
        cost = Decimal(str(row.get("unit_cost", "0") or "0"))
        if sid and cat:
            mapping[(sid, cat)] = cost
    return mapping


def fetch_orders():
    url = f"{BASE_URL}/orders/"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)


def decimal_value(value):
    return Decimal(str(value or 0))


def main():
    products = load_products()
    overrides = load_supplier_product_overrides()
    category_mapping = load_supplier_category_mapping()
    orders = fetch_orders()

    mismatches = []
    for order in orders:
        sku_id = int(order.get("sku_id", 0) or 0)
        supplier_id = int(order.get("supplier_id", 0) or 0)
        qty = decimal_value(order.get("order_quantity"))
        unit_cost = decimal_value(order.get("unit_cost"))
        total_cost = decimal_value(order.get("total_cost"))

        expected_unit = overrides.get((supplier_id, sku_id))
        if expected_unit is None:
            category_id = products.get(sku_id, {}).get("category_id")
            expected_unit = category_mapping.get((supplier_id, category_id))

        expected_total = (qty * unit_cost).quantize(Decimal("0.01"))
        calculated_total = total_cost.quantize(Decimal("0.01"))
        expected_unit_str = f"{expected_unit:.2f}" if expected_unit is not None else "UNKNOWN"

        if calculated_total != expected_total or (expected_unit is not None and unit_cost != expected_unit):
            mismatches.append({
                "order_id": order.get("order_id"),
                "sku_id": sku_id,
                "product_name": products.get(sku_id, {}).get("product_name", ""),
                "supplier_id": supplier_id,
                "order_quantity": str(qty),
                "unit_cost": str(unit_cost),
                "expected_unit_cost": expected_unit_str,
                "total_cost": str(total_cost),
                "expected_total_cost": str(expected_total),
            })

    print(f"Orders verified: {len(orders)}")
    if mismatches:
        print(f"Mismatches found: {len(mismatches)}")
        for item in mismatches:
            print(json.dumps(item, indent=2))
        raise SystemExit(1)
    print("All order rows are consistent: unit_cost * order_quantity == total_cost")


if __name__ == "__main__":
    main()
