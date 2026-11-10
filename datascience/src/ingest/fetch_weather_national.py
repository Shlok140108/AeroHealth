import requests
import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = "/Users/shlokgupta/Documents/aerohealth"
OUT_DIR = os.path.join(PROJECT_ROOT, "datascience", "data", "raw", "weather_national")
cities_df = pd.read_csv(os.path.join(PROJECT_ROOT, "datascience", "data", "raw", "india_cities", "sampled_cities.csv"))

MAX_WORKERS = 10


def fetch_one(row):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": row["lat"], "longitude": row["lon"],
        "start_date": "2023-01-01", "end_date": "2024-12-31",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        daily = resp.json()["daily"]
        rows = []
        for j, date in enumerate(daily["time"]):
            rows.append({
                "city": row["city"], "lat": row["lat"], "lon": row["lon"], "date": date,
                "temp_max": daily["temperature_2m_max"][j],
                "temp_min": daily["temperature_2m_min"][j],
                "precipitation": daily["precipitation_sum"][j],
            })
        return rows
    except Exception as e:
        print(f"Failed for {row['city']}: {e}")
        return []


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    all_rows = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_one, row): row for _, row in cities_df.iterrows()}
        for future in as_completed(futures):
            all_rows.extend(future.result())
            completed += 1
            if completed % 20 == 0:
                print(f"Processed {completed}/{len(cities_df)}, {len(all_rows)} rows so far")
                pd.DataFrame(all_rows).to_csv(os.path.join(OUT_DIR, "progress.csv"), index=False)

    out_df = pd.DataFrame(all_rows)
    out_df.to_csv(os.path.join(OUT_DIR, "national_weather_history.csv"), index=False)
    print(f"\nDone. Saved {len(out_df)} rows across {cities_df.shape[0]} cities")