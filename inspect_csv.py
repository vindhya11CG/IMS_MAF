import csv
import pathlib
base = pathlib.Path('csv_exports')
for db_dir in sorted(base.iterdir()):
    if db_dir.is_dir():
        print('===', db_dir.name, '===')
        for csv_file in sorted(db_dir.glob('*.csv')):
            with csv_file.open('r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, [])
                print(csv_file.name, 'fields=', header)
                row = next(reader, None)
                print(' first row=', row)
                print()
