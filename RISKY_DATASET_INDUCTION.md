# Risky Dataset Induction

## Purpose

This document explains why a risky inventory scenario was induced in the existing CSV dataset and how it was done without changing any database schema.

## Background

The Inventory Management System is designed to detect risky inventory positions and then generate replenishment and supplier selection actions only when risk is present.

During validation, the provided dataset did not contain any inventory positions that met the risk thresholds defined by the system:
- `current_stock <= reorder_point`
- `current_stock <= safety_stock`
- `projected_stock < safety_stock`

As a result, the workflow executed correctly, but Phase 4 and Phase 5 produced zero replenishment orders and zero supplier selections.

## Why the Data Was Induced

The system behavior was correct, but the dataset lacked the low-stock conditions needed to exercise the full workflow.

To validate and demonstrate the complete end-to-end Phase 1-5 pipeline, a controlled risk scenario was introduced into the existing CSV data.

## What Was Changed

- Existing inventory records in `data/csv_exports/db3_csv_export/inventory_positions.csv` were modified.
- Only the existing fields were updated; no schema change was made.
- The induction targeted a subset of inventory positions so that they would satisfy the system's risk conditions.

## Result

- The workflow now detects risky inventory positions in Phase 3.
- Phase 4 generates replenishment orders for the risky items.
- Phase 5 selects suppliers and applies procurement policy to those orders.

## Important Notes

- This is a validation/test dataset change, not a change to system behavior or schema.
- In production, risk should come from actual inventory and demand conditions.
- The induction was implemented using the existing CSV format so that the system remained unchanged and consistent with its current data model.
