from pathlib import Path
import json
import csv

BASE_DIR = Path(__file__).resolve().parents[2]

input_file = BASE_DIR / "data/raw/cpcb/cpcb_backfill_progress.json"
output_file = BASE_DIR / "data/raw/cpcb/cpcb_data.csv"

# Load JSON
with open(input_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# Flatten nested lists
records = []

def flatten(items):
    for item in items:
        if isinstance(item, list):
            flatten(item)
        elif isinstance(item, dict):
            records.append(item)

flatten(data)

print(f"Found {len(records)} records")

if not records:
    print("No dictionary records found.")
    exit()

# Collect all possible columns
fieldnames = set()

for record in records:
    fieldnames.update(record.keys())

fieldnames = list(fieldnames)

# Write CSV
with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames,
        extrasaction="ignore"
    )

    writer.writeheader()
    writer.writerows(records)

print(f"Successfully converted to CSV!")
print(f"Output: {output_file}")