import requests
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

API_KEY = "0bcdf8287e2bb358d43cf4c97892757d84674562427dc2433c692ac8339766d7"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
OUT_DIR = os.path.join(PROJECT_ROOT, "datascience", "data", "raw", "cpcb")

headers = {"X-API-Key": API_KEY}
WANTED_PARAMS = {"pm25", "pm10", "no2", "so2", "o3", "co"}

MAX_WORKERS = 8
SAVE_LOCK = Lock()


def get_india_sensors():
    url = "https://api.openaq.org/v3/locations"
    all_locations = []
    page = 1
    while True:
        params = {"bbox": "68,6,97,37", "limit": 1000, "page": page}
        resp = None
        for attempt in range(5):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                if resp.status_code == 429:
                    time.sleep(10)
                    continue
                resp.raise_for_status()
                break
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                wait = 5 * (attempt + 1)
                print(f"Error page {page}, retry {attempt+1}/5 in {wait}s: {e}")
                time.sleep(wait)
        else:
            print(f"Giving up on page {page}, stopping pagination")
            break

        data = resp.json()["results"]
        if not data:
            break
        all_locations.extend(data)
        print(f"  Fetched page {page}, {len(all_locations)} locations so far")
        page += 1
        time.sleep(0.5)

    sensor_map = []
    skipped = 0
    for loc in all_locations:
        coords = loc.get("coordinates")
        if not coords or coords.get("latitude") is None:
            skipped += 1
            continue
        lat, lon = coords["latitude"], coords["longitude"]
        for sensor in loc.get("sensors", []):
            param_name = sensor["parameter"]["name"]
            if param_name in WANTED_PARAMS:
                sensor_map.append({
                    "sensor_id": sensor["id"], "lat": lat, "lon": lon,
                    "parameter": param_name, "location_name": loc.get("name", "")
                })
    print(f"Skipped {skipped} locations with no coordinates")
    return sensor_map


def fetch_sensor_days(sensor, date_from, date_to, max_retries=3):
    """Never raises — always returns (sensor, results_list), where results_list is [] on any failure."""
    url = f"https://api.openaq.org/v3/sensors/{sensor['sensor_id']}/days"
    params = {"date_from": date_from, "date_to": date_to, "limit": 1000}

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=20)

            if resp.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue

            if resp.status_code in (404, 408, 500, 502, 503):
                # sensor has no data, or a transient server issue — skip quietly, don't crash
                return sensor, []

            resp.raise_for_status()
            return sensor, resp.json()["results"]

        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError,
                requests.exceptions.Timeout) as e:
            wait = 2 * (attempt + 1)
            time.sleep(wait)
        except Exception as e:
            # catch-all so a single sensor's weird failure never kills the batch
            print(f"  Unexpected error for sensor {sensor['sensor_id']}: {e}")
            return sensor, []

    return sensor, []  # exhausted retries


def load_existing_progress():
    path = os.path.join(OUT_DIR, "cpcb_backfill_progress.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_progress(rows):
    with SAVE_LOCK:
        with open(os.path.join(OUT_DIR, "cpcb_backfill_progress.json"), "w") as f:
            json.dump(rows, f)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Fetching India sensor list...")
    sensors = get_india_sensors()
    print(f"Found {len(sensors)} sensors")

    date_from = "2026-05-16"
    date_to = "2026-08-13"

    all_rows = load_existing_progress()
    already_done = {r["sensor_id"] for r in all_rows}
    remaining = [s for s in sensors if s["sensor_id"] not in already_done]
    print(f"{len(remaining)} sensors left — running with {MAX_WORKERS} parallel workers")

    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_sensor_days, s, date_from, date_to): s for s in remaining}

        for future in as_completed(futures):
            try:
                sensor, results = future.result()
            except Exception as e:
                # absolute last resort — should never trigger now, but never let it kill the run
                print(f"Skipping a sensor due to unexpected error: {e}")
                completed += 1
                continue

            for r in results:
                all_rows.append({
                    "sensor_id": sensor["sensor_id"], "lat": sensor["lat"], "lon": sensor["lon"],
                    "parameter": sensor["parameter"], "location_name": sensor["location_name"],
                    "date": r["period"]["datetimeFrom"]["local"], "value": r["value"],
                })

            completed += 1
            if completed % 20 == 0:
                print(f"Processed {completed}/{len(remaining)}, {len(all_rows)} rows so far")
                save_progress(all_rows)

    save_progress(all_rows)  # final save regardless of the %20 checkpoint
    final_path = os.path.join(OUT_DIR, f"cpcb_backfill_{date_from}_to_{date_to}.json")
    with open(final_path, "w") as f:
        json.dump(all_rows, f)
    print(f"DONE. {len(all_rows)} rows saved to {final_path}")