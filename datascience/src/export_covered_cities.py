"""
Builds models/covered_cities.json: the cities the AQI model was actually trained on.
Place at: datascience/src/export_covered_cities.py
Run:      python3 datascience/src/export_covered_cities.py
"""
import os
import json
import pandas as pd

TOP_N = 10          # how many cities the dashboard offers
MIN_ROWS = 1000     # a city needs at least this many daily AQI records in training data

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
arch = os.path.join(ROOT, "archive-2")

day = pd.read_csv(os.path.join(arch, "station_day.csv"), usecols=["StationId", "Date", "AQI"]).dropna(subset=["AQI"])
stations = pd.read_csv(os.path.join(arch, "stations.csv"))[["StationId", "City", "State"]]
coords = pd.read_csv(os.path.join(arch, "city_coordinates.csv"))
coords.columns = coords.columns.str.lower()
coords = coords.rename(columns={"city": "City"}).drop_duplicates("City")[["City", "lat", "lon"]]

df = day.merge(stations, on="StationId").merge(coords, on="City")
g = (df.groupby(["City", "State", "lat", "lon"]).agg(rows=("AQI", "size")).reset_index()
       .query("rows >= @MIN_ROWS").sort_values("rows", ascending=False).head(TOP_N))

cities = [{
    "name": r.City, "state": r.State, "lat": round(r.lat, 4), "lon": round(r.lon, 4),
    "label": r.City if r.City == r.State else f"{r.City}, {r.State}",
} for r in g.itertuples()]

out = os.path.join(ROOT, "models", "covered_cities.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(cities, f, indent=2)

print(f"Saved {len(cities)} cities to {out}")
for c in cities:
    print("  ", c["label"])