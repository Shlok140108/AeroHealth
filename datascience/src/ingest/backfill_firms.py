import requests
import os
from datetime import datetime, timedelta

MAP_KEY = "66bfa85864148c31708a146adc5b08aa"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUT_DIR = os.path.join(PROJECT_ROOT, "datascience", "data", "raw", "firms")

def fetch_historical(date_str):
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_SP/68,6,97,37/1/{date_str}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    end_date = datetime.now()
    for i in range(30):
        date = end_date - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        try:
            csv_data = fetch_historical(date_str)
            path = os.path.join(OUT_DIR, f"{date_str}.csv")
            with open(path, "w") as f:
                f.write(csv_data)
            print(f"Saved {date_str}")
        except Exception as e:
            print(f"Failed {date_str}: {e}")