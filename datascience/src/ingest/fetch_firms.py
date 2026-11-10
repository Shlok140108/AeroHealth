import requests
import os
from datetime import datetime

MAP_KEY = "66bfa85864148c31708a146adc5b08aa"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUT_DIR = os.path.join(PROJECT_ROOT, "datascience", "data", "raw", "firms")

def fetch_fires():
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/68,6,97,37/1"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    csv_data = fetch_fires()
    path = os.path.join(OUT_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.csv")
    with open(path, "w") as f:
        f.write(csv_data)
    print(f"Saved {path}")