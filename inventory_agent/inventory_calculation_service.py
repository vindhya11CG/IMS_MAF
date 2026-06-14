from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List, Optional, Tuple

from .models import InventoryCalculationResult, InventoryPosition, InventorySnapshot
from .service_base import AgentService


class InventoryCalculationService(AgentService):
    """Service that calculates current inventory stock for each SKU and location."""

    def __init__(self) -> None:
        super().__init__(name="InventoryCalculationService")

    def execute(
        self,
        positions: Iterable[InventoryPosition],
        snapshots: Iterable[InventorySnapshot],
    ) -> List[InventoryCalculationResult]:
        return self.calculate_current_stock(list(positions), list(snapshots))

    def calculate_current_stock(
        self,
        positions: List[InventoryPosition],
        snapshots: List[InventorySnapshot],
    ) -> List[InventoryCalculationResult]:
        snapshot_map = self._group_snapshots_by_key(snapshots)
        position_map = self._group_positions_by_key(positions)
        results: List[InventoryCalculationResult] = []

        for key, snapshot in snapshot_map.items():
            result = self._calculate_from_snapshot(snapshot)
            results.append(result)

        for key, position in position_map.items():
            if key in snapshot_map:
                continue
            results.append(
                InventoryCalculationResult(
                    sku_id=position.sku_id,
                    location_id=position.location_id,
                    current_stock=position.on_hand_qty,
                    previous_stock=position.on_hand_qty,
                    sales=0,
                    incoming_stock=0,
                    adjustments=0,
                    source="inventory_positions",
                )
            )

        return results

    def _calculate_from_snapshot(self, snapshot: InventorySnapshot) -> InventoryCalculationResult:
        current_stock = (
            snapshot.opening_stock
            - snapshot.sales
            + snapshot.receipts
            + snapshot.transfers_in
            - snapshot.transfers_out
            + snapshot.adjustments
        )

        return InventoryCalculationResult(
            sku_id=snapshot.sku_id,
            location_id=snapshot.location_id,
            current_stock=current_stock,
            previous_stock=snapshot.opening_stock,
            sales=snapshot.sales,
            incoming_stock=snapshot.receipts + snapshot.transfers_in,
            adjustments=snapshot.adjustments - snapshot.transfers_out,
            source="inventory_daily_snapshots",
        )

    def _group_snapshots_by_key(
        self, snapshots: Iterable[InventorySnapshot]
    ) -> dict[Tuple[int, int], InventorySnapshot]:
        grouped: dict[Tuple[int, int], InventorySnapshot] = {}
        for snapshot in snapshots:
            grouped[(snapshot.sku_id, snapshot.location_id)] = snapshot
        return grouped

    def _group_positions_by_key(
        self, positions: Iterable[InventoryPosition]
    ) -> dict[Tuple[int, int], InventoryPosition]:
        grouped: dict[Tuple[int, int], InventoryPosition] = {}
        for position in positions:
            grouped[(position.sku_id, position.location_id)] = position
        return grouped
