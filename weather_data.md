# Weather Data Download Guide (Kaggle) — Temperature & Precipitation

## Dataset
**India Daily Weather (2000–2024) – Major Cities**
https://www.kaggle.com/datasets/developerghost/climate-in-india-daily-weather-data-2000-2024

Daily data, 10 major Indian cities, 24 years of history — includes temperature and precipitation.

---

## Step 1 — Get your Kaggle API token (skip if you already have one from the AQI dataset)

1. Go to https://www.kaggle.com/settings
2. Scroll to "API" section → click "Create New Token"
3. This downloads `kaggle.json`
4. Move it to the right place:
```bash
mkdir -p ~/.kaggle
mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
```
---

## Step 2 — Install the Kaggle CLI (skip if already installed)

```bash
pip install kaggle --break-system-packages
```

---

## Step 3 — Download the dataset

```bash
cd ~/Documents/aerohealth
mkdir -p archive-weather
cd archive-weather
kaggle datasets download -d developerghost/climate-in-india-daily-weather-data-2000-2024
unzip climate-in-india-daily-weather-data-2000-2024.zip
cd ..
```

---

## Step 4 — Inspect the actual column names (critical before writing training code)

```python
import pandas as pd

df = pd.read_csv("archive-weather/india_2000_2024_daily_weather.csv")
print("Columns:", df.columns.tolist())
print("\nShape:", df.shape)
print("\nSample rows:")
print(df.head())
print("\nUnique cities:", df["city"].unique())  # adjust column name once confirmed
print("\nMissing values per column:")
print(df.isna().sum())
```

Run this and note down the exact column names for:
- City name column
- Date column
- Temperature column(s) — may be `temp_avg`, `temperature`, `Temperature_Avg`, etc.
- Precipitation column — may be `precipitation`, `rainfall`, `Rainfall`, etc.

---

## Step 5 — Geocode the 10 cities (reuse your existing geocoding script if these cities overlap your AQI dataset's cities)

```python
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time

geolocator = Nominatim(user_agent="vayudrishti_weather")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, max_retries=3)

cities = df["city"].unique()  # adjust column name
city_coords = {}

for city in cities:
    try:
        location = geocode(f"{city}, India")
        if location:
            city_coords[city] = (location.latitude, location.longitude)
            print(f"✓ {city}: {location.latitude}, {location.longitude}")
        else:
            print(f"✗ Not found: {city}")
    except Exception as e:
        print(f"✗ Error for {city}: {e}")

coords_df = pd.DataFrame([
    {"city": city, "lat": lat, "lon": lon}
    for city, (lat, lon) in city_coords.items()
])
coords_df.to_csv("archive-weather/city_coordinates.csv", index=False)
print(f"\nSaved {len(coords_df)} city coordinates")
```

Only 10 cities — this finishes in under 15 seconds.

---

## Step 6 — Merge coordinates into the main dataframe

```python
coords_df = pd.read_csv("archive-weather/city_coordinates.csv")
df = df.merge(coords_df, on="city", how="left")  # adjust column name to match

print(f"Rows missing coordinates: {df['lat'].isna().sum()} / {len(df)}")
df = df.dropna(subset=["lat", "lon"])

df.to_csv("archive-weather/weather_with_coords.csv", index=False)
print(f"Saved {len(df)} rows with coordinates")
```

---

## Step 7 — Quick sanity check before training

```python
df = pd.read_csv("archive-weather/weather_with_coords.csv")

# Check value ranges make sense
print("Temperature range:", df["temp_avg"].min(), "-", df["temp_avg"].max())  # adjust column
print("Precipitation range:", df["precipitation"].min(), "-", df["precipitation"].max())  # adjust column

# Check how many days have zero rain (expected to be high — most days don't rain)
zero_rain_pct = (df["precipitation"] == 0).mean() * 100
print(f"Days with zero precipitation: {zero_rain_pct:.1f}%")
```

If temperature values look like reasonable Celsius numbers (roughly 5-50) and precipitation is mostly 0 with occasional higher values, you're ready to move to training.

---

## Next step
Once this is done and columns are confirmed, move to the training script (temp + precipitation XGBoost models) — same structure as your AQI model, just swap in these features and targets.