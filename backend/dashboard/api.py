"""
Place at: backend/dashboard/api.py
Serves GET /api/overview/?lat=18.52&lon=73.86&place=Pune
Weather + pollutant forecasts come from Open-Meteo; pollutants go through the trained AQI model.
"""
import json
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

from weather.ml_service import AQI_FEATURES, predict_aqi_batch, predict_temperature

IST = ZoneInfo("Asia/Kolkata")
NAN = float("nan")
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _get(url, params):
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _n(x):
    return NAN if x is None else x


def _clock(hour):                       # 17 -> "5 PM"
    return f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"


def _hm(t):                             # datetime -> "6:04 AM"
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _desc(code):
    if code == 0: return "Clear sky"
    if code in (1, 2): return "Partly cloudy"
    if code == 3: return "Overcast"
    if code in (45, 48): return "Fog"
    if code in (51, 53, 55, 56, 57): return "Drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82): return "Rain"
    if code >= 95: return "Thunderstorm"
    return "Cloudy"


def _uv(v):
    v = v or 0
    label = "Low" if v < 3 else "Moderate" if v < 6 else "High" if v < 8 else "Very high" if v < 11 else "Extreme"
    return f"{round(v)} · {label}"


INDIA_LAT = (6.0, 37.5)
INDIA_LON = (68.0, 98.0)


def in_india(lat, lon):
    return INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]


def parse_coords(request, default=(28.61, 77.21), india_only=False):
    """Read ?lat=&lon= -> (lat, lon) rounded to 2 dp (~1 km, also the cache key).
    Raises ValueError with a user-facing message for bad input."""
    try:
        lat = float(request.GET.get("lat", default[0]))
        lon = float(request.GET.get("lon", default[1]))
    except (TypeError, ValueError):
        raise ValueError("lat and lon must be numbers")
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("lat must be between -90 and 90 and lon between -180 and 180")
    if india_only and not in_india(lat, lon):
        raise ValueError("The AQI model was trained on Indian data; pick a location in India")
    return round(lat, 2), round(lon, 2)


def _aqi_series(air, indices, lat, lon):
    """CPCB-scale AQI estimate for each hourly index (None where PM data is missing).
    One batched model call instead of one per hour."""
    h, rows, slots = air["hourly"], [], []
    for pos, i in enumerate(indices):
        try:
            pm25, pm10 = h["pm2_5"][i], h["pm10"][i]
        except IndexError:
            continue
        if pm25 is None or pm10 is None:
            continue
        co = h["carbon_monoxide"][i]                  # Open-Meteo: ug/m3, CPCB dataset: mg/m3
        when = datetime.fromisoformat(h["time"][i])
        rows.append(dict(zip(AQI_FEATURES, [
            pm25, pm10, NAN, _n(h["nitrogen_dioxide"][i]), NAN, NAN,
            NAN if co is None else co / 1000, _n(h["sulphur_dioxide"][i]), _n(h["ozone"][i]),
            NAN, NAN, lat, lon, when.month, when.weekday()])))
        slots.append(pos)
    out = [None] * len(indices)
    for pos, v in zip(slots, predict_aqi_batch(rows)):
        out[pos] = round(v)
    return out


def build(lat, lon):
    w = _get(WEATHER_URL, {
        "latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 7,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,uv_index",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,sunrise,sunset",
    })
    air = _get(AIR_URL, {
        "latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 2,
        "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
    })
    now = datetime.now(IST)
    h = now.hour
    hw, dw, cur = w["hourly"], w["daily"], w["current"]

    aqi = _aqi_series(air, [h + k for k in range(24)], lat, lon)
    if aqi[0] is None:
        raise ValueError("No pollutant data for this location")
    for k in range(1, 24):
        if aqi[k] is None:
            aqi[k] = aqi[k - 1]

    rain = lambda i: hw["precipitation_probability"][i] or 0
    peak = max(range(24), key=lambda k: aqi[k])
    note = (f"A rise to {aqi[peak]} is predicted around {_clock((h + peak) % 24)}."
            if peak > 0 and aqi[peak] >= aqi[0] + 10 else "Air quality is expected to stay steady today.")

    best = None                                    # calmest, driest 2-hour daytime window
    for k in range(23):
        s = (h + k) % 24
        if 6 <= s <= 19:
            score = (aqi[k] + aqi[k + 1]) / 2 + max(rain(h + k), rain(h + k + 1)) * 0.5
            if best is None or score < best[0]:
                best = (score, k)
    k = best[1]
    start = (h + k) % 24
    avg = round((aqi[k] + aqi[k + 1]) / 2)

    return {
        "user": {"name": "Maya Patel", "persona": "Asthma-aware", "sensitivity": "High"},  # TODO: read from UserProfile
        "updated": f"Updated at {_hm(now)} IST",
        "weather": {
            "temp": round(cur["temperature_2m"]), "desc": _desc(cur["weather_code"]),
            "feels": round(cur["apparent_temperature"]),
            "hi": round(dw["temperature_2m_max"][0]), "lo": round(dw["temperature_2m_min"][0]),
            "wind": round(cur["wind_speed_10m"]), "humidity": round(cur["relative_humidity_2m"]),
            "uv": _uv(hw["uv_index"][h]),
        },
        "aqi": {
            "value": aqi[0], "source": "Model estimate", "note": note,
            "pm25": round(air["hourly"]["pm2_5"][h] or 0), "pm10": round(air["hourly"]["pm10"][h] or 0),
            "o3": round(air["hourly"]["ozone"][h] or 0), "no2": round(air["hourly"]["nitrogen_dioxide"][h] or 0),
        },
        "hourly": [["Now" if k == 0 else _clock((h + k) % 24), round(hw["temperature_2m"][h + k]), aqi[k], rain(h + k)]
                   for k in range(8)],
        "week": [["Today" if i == 0 else datetime.fromisoformat(dw["time"][i]).strftime("%a"),
                  round(dw["temperature_2m_min"][i]), round(dw["temperature_2m_max"][i]),
                  dw["precipitation_probability_max"][i] or 0] for i in range(7)],
        "curve": aqi[::2],
        "sun": {"rise": _hm(datetime.fromisoformat(dw["sunrise"][0])), "set": _hm(datetime.fromisoformat(dw["sunset"][0]))},
        "rain": f"{(dw['precipitation_sum'][0] or 0):.1f} mm today",
        "outside": {
            "window": f"{_clock(start)} – {_clock((start + 2) % 24)}", "aqi": avg,
            "text": ("Cleaner air and low rain odds line up for time outside." if avg <= 100
                     else "The best stretch of the day, but keep outdoor effort light."),
        },
    }


def overview_api(request):
    try:
        lat, lon = parse_coords(request, india_only=True)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    key = f"overview:{lat}:{lon}"
    data = cache.get(key)
    if data is None:
        try:
            data = build(lat, lon)
        except Exception as e:                      # the page falls back to sample data on any non-200
            return JsonResponse({"error": str(e)}, status=502)
        cache.set(key, data, 600)                   # 10-minute cache
    return JsonResponse(dict(data, place=request.GET.get("place", "Delhi")))


# Used only if models/covered_cities.json has not been generated yet
FALLBACK_CITIES = [
    {"name": "Delhi", "state": "Delhi", "lat": 28.6139, "lon": 77.209, "label": "Delhi"},
    {"name": "Mumbai", "state": "Maharashtra", "lat": 19.076, "lon": 72.8777, "label": "Mumbai, Maharashtra"},
    {"name": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lon": 88.3639, "label": "Kolkata, West Bengal"},
    {"name": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707, "label": "Chennai, Tamil Nadu"},
    {"name": "Hyderabad", "state": "Telangana", "lat": 17.385, "lon": 78.4867, "label": "Hyderabad, Telangana"},
    {"name": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946, "label": "Bengaluru, Karnataka"},
]


def cities_api(request):
    """GET /api/cities/ -> the cities the AQI model was trained on."""
    try:
        with open(os.path.join(settings.BASE_DIR, "models", "covered_cities.json")) as f:
            cities = json.load(f)
    except (OSError, ValueError):
        cities = FALLBACK_CITIES
    return JsonResponse({"cities": cities})


# ---------------- Prediction page ----------------
CPCB = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
HEADLINES = ["Air is clean.", "Air is acceptable for most people.", "Sensitive groups should take care.",
             "Most people may feel discomfort outdoors.", "Avoid prolonged time outdoors.", "Stay indoors where possible."]
GROUPS = [  # (who, [text for tiers: low, moderate, poor, very poor/severe])
    ("Asthma & lung conditions", ["No special steps; carry your inhaler as usual.",
        "Keep your reliever inhaler close and limit hard exercise outdoors.",
        "Avoid outdoor exertion and follow your doctor's action plan.",
        "Stay indoors and contact your doctor if breathing worsens."]),
    ("Children & older adults", ["Normal outdoor play is fine.", "Shorten long outdoor activity.",
        "Keep outdoor time short; prefer indoor play.", "Stay indoors; avoid outdoor exertion."]),
    ("Heart conditions", ["No special steps.", "Avoid heavy exertion outdoors.",
        "Avoid exertion; watch for chest discomfort or unusual tiredness.", "Stay indoors and seek care if symptoms appear."]),
    ("Outdoor workers & commuters", ["No special steps.", "Take breaks in cleaner air when you can.",
        "Wear an N95-type mask and take frequent breaks.", "Limit outdoor work; wear an N95-type mask if you must go out."]),
]
ACTIONS = [["Good day for outdoor exercise and open windows."],
           ["Plan harder workouts for the cleanest hours of the day."],
           ["Exercise indoors or in the cleanest hours.", "Keep windows closed during peak hours.", "Consider an air purifier."],
           ["Keep windows closed and stay indoors.", "Use an air purifier if you have one.", "Postpone outdoor exercise."]]


def _advice(aqi_max, hi, rain, uv):
    band = next((i for i, m in enumerate((50, 100, 200, 300, 400)) if aqi_max <= m), 5)
    tier = 0 if band <= 1 else 1 if band == 2 else 2 if band == 3 else 3
    actions = list(ACTIONS[tier])
    if hi >= 40: actions.append("Very hot: drink plenty of water and avoid the midday sun.")
    elif hi >= 35: actions.append("Hot afternoon: stay hydrated and avoid peak sun.")
    if rain >= 60: actions.append("Rain is likely: carry an umbrella. Rain can briefly clear the air.")
    if uv >= 8: actions.append("High UV: use sunscreen and a hat.")
    return {"band": CPCB[band], "headline": HEADLINES[band], "basis": f"Based on today's peak AQI of {aqi_max}",
            "groups": [{"who": w, "text": t[tier]} for w, t in GROUPS], "actions": actions}


def build_prediction(lat, lon):
    w = _get(WEATHER_URL, {"latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 7,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,uv_index_max"})
    air = _get(AIR_URL, {"latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 5,
        "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"})
    d = w["daily"]
    air_days = len(air["hourly"]["time"]) // 24
    days = []
    for i in range(7):
        vals = []
        if i < air_days:
            vals = [v for v in _aqi_series(air, [i * 24 + hr for hr in range(0, 24, 3)], lat, lon)
                    if v is not None]                         # sample every 3 hours
        days.append({
            "day": "Today" if i == 0 else datetime.fromisoformat(d["time"][i]).strftime("%a"),
            "hi": round(d["temperature_2m_max"][i]), "lo": round(d["temperature_2m_min"][i]),
            "rain": d["precipitation_probability_max"][i] or 0, "rain_mm": round(d["precipitation_sum"][i] or 0, 1),
            "aqi_avg": round(sum(vals) / len(vals)) if vals else None, "aqi_max": max(vals) if vals else None,
        })
    if days[0]["aqi_max"] is None:
        raise ValueError("No pollutant data for this location")
    try:
        typical = round(predict_temperature(lat, lon)[0])   # the trained model's typical high/avg for today's date
    except Exception:
        typical = None
    return {"days": days, "typical_temp_today": typical,
            "advice": _advice(days[0]["aqi_max"], days[0]["hi"], days[0]["rain"], d["uv_index_max"][0] or 0),
            "updated": f"Updated at {_hm(datetime.now(IST))} IST"}


def prediction_api(request):
    try:
        lat, lon = parse_coords(request, india_only=True)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    key = f"prediction:{lat}:{lon}"
    data = cache.get(key)
    if data is None:
        try:
            data = build_prediction(lat, lon)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=502)
        cache.set(key, data, 600)
    return JsonResponse(dict(data, place=request.GET.get("place", "Delhi")))