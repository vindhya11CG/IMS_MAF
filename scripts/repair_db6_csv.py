import csv
from pathlib import Path

source = Path('data/csv_exports/db6_csv_export/demand_context_fact.csv')
rows = list(csv.reader(source.open(encoding='utf-8-sig', newline='')))
header = rows[0]
short_rows = []
patched_rows = [rows[0]]
for row in rows[1:]:
    if len(row) < len(header):
        short_rows.append(len(patched_rows))
        row = row + [''] * (len(header) - len(row))
    patched_rows.append(row)

with source.open('w', encoding='utf-8', newline='') as fh:
    writer = csv.writer(fh)
    writer.writerows(patched_rows)

print('patched short rows', len(short_rows))
print('new header fields', len(rows[0]))
print('row length counts', sorted({len(r) for r in rows[1:]}))
