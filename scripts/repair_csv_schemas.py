from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Tuple


def repair_csv(path: Path) -> Tuple[int, int]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        return 0, 0

    header = rows[0]
    repaired_rows: List[List[str]] = [header]
    fixed_rows = 0

    for row in rows[1:]:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
            fixed_rows += 1
        elif len(row) > len(header):
            row = row[: len(header)]
            fixed_rows += 1
        repaired_rows.append(row)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(repaired_rows)

    return len(repaired_rows) - 1, fixed_rows


if __name__ == "__main__":
    targets = [
        Path("data/csv_exports/db6_csv_export/demand_context_fact.csv"),
        Path("data/csv_exports/db1_csv_export/distribution_centers.csv"),
    ]
    for target in targets:
        row_count, fixed_rows = repair_csv(target)
        print(f"{target}: {row_count} rows processed, {fixed_rows} rows repaired")
