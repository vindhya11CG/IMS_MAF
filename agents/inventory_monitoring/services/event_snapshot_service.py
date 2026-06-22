"""Phase 1: Inventory Event Snapshot Service

Loads and validates inventory event snapshots from the data source (DB5).
This is the foundation for all subsequent calculations and risk assessments.
"""

import logging
from typing import Dict, List
from dataclasses import dataclass

from agents.inventory_monitoring.models.inventory_models import InventorySnapshot
from utils.csv_loader import CsvInventoryDataLoader
from utils.parsing import parse_int, parse_optional_int

logger = logging.getLogger(__name__)


@dataclass
class SnapshotValidationResult:
    """Result of snapshot validation."""
    valid_snapshots: List[InventorySnapshot]
    invalid_count: int
    errors: List[str]
    total_loaded: int


class EventSnapshotService:
    """Phase 1: Load and validate inventory event snapshots from data source."""

    def __init__(self, data_loader: CsvInventoryDataLoader | None = None):
        """Initialize the Event Snapshot Service.
        
        Args:
            data_loader: CSV data loader instance. If None, creates a default one.
        """
        self.data_loader = data_loader or CsvInventoryDataLoader()

    def execute(self) -> SnapshotValidationResult:
        """Load and validate all inventory event snapshots.
        
        Returns:
            SnapshotValidationResult with valid snapshots and validation errors
        """
        logger.info("="*80)
        logger.info("PHASE 1: INVENTORY EVENT SNAPSHOT SERVICE - STARTING")
        logger.info("="*80)
        
        # Load raw snapshot data from CSV
        raw_snapshots = self._load_raw_snapshots()
        logger.info(f"Loaded {len(raw_snapshots)} raw snapshot records from CSV")
        
        # Validate and convert to InventorySnapshot objects
        valid_snapshots = []
        invalid_count = 0
        errors = []
        
        for idx, raw_snapshot in enumerate(raw_snapshots):
            try:
                snapshot = self._validate_and_convert(raw_snapshot, idx)
                valid_snapshots.append(snapshot)
            except ValueError as e:
                invalid_count += 1
                errors.append(str(e))
                if invalid_count <= 5:  # Log first 5 errors
                    logger.warning(f"Invalid snapshot at index {idx}: {e}")
        
        if invalid_count > 5:
            logger.warning(f"... and {invalid_count - 5} more validation errors (not shown)")
        
        # Log summary
        logger.info(f"Snapshot Validation Summary:")
        logger.info(f"  Total loaded: {len(raw_snapshots)}")
        logger.info(f"  Valid: {len(valid_snapshots)}")
        logger.info(f"  Invalid: {invalid_count}")
        logger.info(f"  Success rate: {len(valid_snapshots)/max(len(raw_snapshots), 1)*100:.1f}%")
        
        # Group snapshots by date for summary
        snapshot_dates = {}
        for snapshot in valid_snapshots:
            date_key = snapshot.snapshot_date
            snapshot_dates[date_key] = snapshot_dates.get(date_key, 0) + 1
        
        if snapshot_dates:
            min_date = min(snapshot_dates.keys())
            max_date = max(snapshot_dates.keys())
            logger.info(f"  Date range: {min_date} to {max_date}")
            logger.info(f"  Unique dates: {len(snapshot_dates)}")
        
        logger.info("PHASE 1: COMPLETE")
        logger.info("="*80)
        
        return SnapshotValidationResult(
            valid_snapshots=valid_snapshots,
            invalid_count=invalid_count,
            errors=errors,
            total_loaded=len(raw_snapshots),
        )

    def _load_raw_snapshots(self) -> List[Dict]:
        """Load raw snapshot data from CSV.
        
        Returns:
            List of dictionaries containing raw snapshot data
        """
        return self.data_loader.load_inventory_daily_snapshots()

    def _validate_and_convert(self, raw_snapshot: Dict, index: int) -> InventorySnapshot:
        """Validate raw snapshot data and convert to InventorySnapshot object.
        
        Args:
            raw_snapshot: Raw snapshot dictionary from CSV
            index: Index in the dataset (for error reporting)
            
        Returns:
            Validated InventorySnapshot object
            
        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        required_fields = [
            "snapshot_id", "snapshot_date", "sku_id", "location_id",
            "opening_stock", "closing_stock"
        ]
        
        for field in required_fields:
            if field not in raw_snapshot or raw_snapshot[field] is None:
                raise ValueError(f"Missing required field: {field} at index {index}")
        
        try:
            snapshot_id = parse_int(raw_snapshot.get("snapshot_id"), 0)
            if snapshot_id == 0:
                raise ValueError("snapshot_id cannot be empty or invalid")
            
            snapshot_date = str(raw_snapshot.get("snapshot_date", "")).strip()
            if not snapshot_date:
                raise ValueError("snapshot_date cannot be empty")
            
            sku_id = parse_int(raw_snapshot.get("sku_id") or raw_snapshot.get("product_id"), 0)
            if sku_id == 0:
                raise ValueError("sku_id/product_id cannot be empty or invalid")
            
            location_id = parse_int(raw_snapshot.get("location_id"), 0)
            if location_id == 0:
                raise ValueError("location_id cannot be empty or invalid")
            
            # Parse numeric fields with defaults
            opening_stock = parse_int(raw_snapshot.get("opening_stock"), 0)
            closing_stock = parse_int(raw_snapshot.get("closing_stock"), 0)
            sales = parse_int(raw_snapshot.get("sales"), 0)
            receipts = parse_int(raw_snapshot.get("receipts"), 0)
            transfers_in = parse_int(raw_snapshot.get("transfers_in"), 0)
            transfers_out = parse_int(raw_snapshot.get("transfers_out"), 0)
            adjustments = parse_optional_int(raw_snapshot.get("adjustments"))
            
            # Validate stock levels (sanity check)
            if opening_stock < 0:
                raise ValueError(f"Invalid opening_stock: {opening_stock} (must be >= 0)")
            if closing_stock < 0:
                raise ValueError(f"Invalid closing_stock: {closing_stock} (must be >= 0)")
            
            # Create snapshot object
            snapshot = InventorySnapshot(
                snapshot_id=snapshot_id,
                snapshot_date=snapshot_date,
                sku_id=sku_id,
                location_id=location_id,
                opening_stock=opening_stock,
                receipts=receipts,
                sales=sales,
                transfers_in=transfers_in,
                transfers_out=transfers_out,
                adjustments=adjustments if adjustments is not None else 0,
                closing_stock=closing_stock,
            )
            
            return snapshot
            
        except (ValueError, KeyError, AttributeError) as e:
            raise ValueError(f"Failed to convert snapshot at index {index}: {e}")

    def get_snapshots_by_location(self, snapshots: List[InventorySnapshot]) -> Dict[str, List[InventorySnapshot]]:
        """Group snapshots by location.
        
        Args:
            snapshots: List of snapshots to group
            
        Returns:
            Dictionary mapping location_id to list of snapshots
        """
        grouped = {}
        for snapshot in snapshots:
            if snapshot.location_id not in grouped:
                grouped[snapshot.location_id] = []
            grouped[snapshot.location_id].append(snapshot)
        return grouped

    def get_snapshots_by_sku(self, snapshots: List[InventorySnapshot]) -> Dict[str, List[InventorySnapshot]]:
        """Group snapshots by SKU.
        
        Args:
            snapshots: List of snapshots to group
            
        Returns:
            Dictionary mapping sku_id to list of snapshots
        """
        grouped = {}
        for snapshot in snapshots:
            if snapshot.sku_id not in grouped:
                grouped[snapshot.sku_id] = []
            grouped[snapshot.sku_id].append(snapshot)
        return grouped

    def get_snapshots_by_location_and_sku(
        self, snapshots: List[InventorySnapshot]
    ) -> Dict[tuple, List[InventorySnapshot]]:
        """Group snapshots by location-SKU combination.
        
        Args:
            snapshots: List of snapshots to group
            
        Returns:
            Dictionary mapping (location_id, sku_id) tuple to list of snapshots
        """
        grouped = {}
        for snapshot in snapshots:
            key = (snapshot.location_id, snapshot.sku_id)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(snapshot)
        return grouped
