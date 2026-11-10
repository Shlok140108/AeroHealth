import requests
import json
from datetime import datetime
import os

API_KEY = "YOUR_OPENAQ_KEY_HERE"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUT_DIR = os.path.join(PROJECT_ROOT, "datascience", "data", "raw", "cpcb")

def fetch_india_stations():
    url = "https://api.openaq.org/v3/locations"
    headers = {"X-API-Key": API_KEY}
    params = {"bbox": "68,6,97,37", "limit": 1000}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    data = fetch_india_stations()
    filename = os.path.join(OUT_DIR, f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.json")
    with open(filename, "w") as f:
        json.dump(data, f)
    print(f"Saved {filename}")