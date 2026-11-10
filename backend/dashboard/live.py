"""
Live weather endpoints for the conventional weather-app page and the live location tracker.

  GET /api/live/?lat=&lon=      current conditions + 24h + 7 days + details + AQI (worldwide)
  GET /api/geocode/?q=Pune      city search (Open-Meteo geocoding)
  GET /api/reverse/?lat=&lon=   coordinates -> place name (OpenStreetMap Nominatim)

All upstream hosts are fixed (no user-supplied URLs). Responses are cached briefly so
a moving user does not hammer the free upstream APIs.
"""
from datetime import datetime, timezone

import requests
from django.core.cache import cache
from django.http import JsonResponse

from .api import AIR_URL, WEATHER_URL, _get, in_india, parse_coords
from weather.ml_service import AQI_FEATURES, predict_aqi_batch

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "AeroHealth/1.0 (student project; local development)"   # Nominatim policy requires one

LIVE_TTL = 300          # Open-Meteo "current" refreshes every 15 min; 5 min cache keeps it feeling live
NAN = float("nan")

# WMO weather code -> (label, day icon, night icon)
WMO = {
    0: ("Clear sky", "☀️", "🌙"), 1: ("Mainly clear", "🌤️", "🌙"), 2: ("Partly cloudy", "⛅", "☁️"),
    3: ("Overcast", "☁️", "☁️"), 45: ("Fog", "🌫️", "🌫️"), 48: ("Rime fog", "🌫️", "🌫️"),
    51: ("Light drizzle", "🌦️", "🌧️"), 53: ("Drizzle", "🌦️", "🌧️"), 55: ("Heavy drizzle", "🌧️", "🌧️"),
    56: ("Freezing drizzle", "🌧️", "🌧️"), 57: ("Freezing drizzle", "🌧️", "🌧️"),
    61: ("Light rain", "🌦️", "🌧️"), 63: ("Rain", "🌧️", "🌧️"), 65: ("Heavy rain", "🌧️", "🌧️"),
    66: ("Freezing rain", "🌧️", "🌧️"), 67: ("Freezing rain", "🌧️", "🌧️"),
    71: ("Light snow", "🌨️", "🌨️"), 73: ("Snow", "🌨️", "🌨️"), 75: ("Heavy snow", "❄️", "❄️"),
    77: ("Snow grains", "🌨️", "🌨️"), 80: ("Light showers", "🌦️", "🌧️"), 81: ("Showers", "🌧️", "🌧️"),
    82: ("Violent showers", "⛈️", "⛈️"), 85: ("Snow showers", "🌨️", "🌨️"), 86: ("Heavy snow showers", "❄️", "❄️"),
    95: ("Thunderstorm", "⛈️", "⛈️"), 96: ("Thunderstorm, hail", "⛈️", "⛈️"), 99: ("Severe thunderstorm", "⛈️", "⛈️"),
}
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def wmo(code, is_day=1):
    label, day, night = WMO.get(code, ("Unknown", "🌡️", "🌡️"))
    return label, (day if is_day else night)


def _round(v, nd=0):
    if v is None:
        return None
    return round(v) if nd == 0 else round(v, nd)


def _theme(code, is_day):
    """Background theme key for the hero card."""
    if code in (95, 96, 99): return "storm"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82): return "rain"
    if code in (71, 73, 75, 77, 85, 86): return "snow"
    if code in (45, 48): return "fog"
    if code == 3: return "cloud-day" if is_day else "cloud-night"
    return "clear-day" if is_day else "clear-night"


def _clock(iso):                                  # "2026-11-10T06:04" -> "6:04 AM"
    t = datetime.fromisoformat(iso)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _hour_label(iso):
    t = datetime.fromisoformat(iso)
    return f"{t.hour % 12 or 12} {'AM' if t.hour < 12 else 'PM'}"


def _uv_label(v):
    v = v or 0
    return "Low" if v < 3 else "Moderate" if v < 6 else "High" if v < 8 else "Very high" if v < 11 else "Extreme"


def _fetch_aqi(lat, lon):
    """Current air quality. Returns None if the air-quality API is unavailable (weather still works)."""
    try:
        a = _get(AIR_URL, {"latitude": lat, "longitude": lon, "timezone": "auto",
                           "current": "us_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone"})["current"]
    except Exception:
        return None
    out = {"us_aqi": _round(a.get("us_aqi")), "pm25": _round(a.get("pm2_5")), "pm10": _round(a.get("pm10")),
           "no2": _round(a.get("nitrogen_dioxide")), "o3": _round(a.get("ozone")),
           "cpcb": None, "cpcb_source": None}
    if in_india(lat, lon) and a.get("pm2_5") is not None and a.get("pm10") is not None:
        try:                                                # trained model only makes sense for Indian stations
            when = datetime.fromisoformat(a["time"])
            co = a.get("carbon_monoxide")
            row = dict(zip(AQI_FEATURES, [
                a["pm2_5"], a["pm10"], NAN, a.get("nitrogen_dioxide") if a.get("nitrogen_dioxide") is not None else NAN, NAN, NAN,
                NAN if co is None else co / 1000,
                a.get("sulphur_dioxide") if a.get("sulphur_dioxide") is not None else NAN,
                a.get("ozone") if a.get("ozone") is not None else NAN,
                NAN, NAN, lat, lon, when.month, when.weekday()]))
            out["cpcb"] = round(predict_aqi_batch([row])[0])
            out["cpcb_source"] = "AeroHealth model estimate"
        except Exception:
            pass
    return out


def build_live(lat, lon):
    w = _get(WEATHER_URL, {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7, "wind_speed_unit": "kmh",
        "current": ("temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,"
                    "cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m"),
        "hourly": "temperature_2m,precipitation_probability,weather_code,is_day,visibility,dew_point_2m,uv_index",
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                  "precipitation_sum,sunrise,sunset,uv_index_max"),
    })
    cur, hw, dw = w["current"], w["hourly"], w["daily"]
    is_day = cur.get("is_day", 1)
    label, icon = wmo(cur["weather_code"], is_day)

    # index of the current hour inside the hourly arrays (times are local to the location)
    now_hour = cur["time"][:13]
    start = next((i for i, t in enumerate(hw["time"]) if t[:13] == now_hour), 0)

    hourly = []
    for i in range(start, min(start + 24, len(hw["time"]))):
        _, ic = wmo(hw["weather_code"][i], hw["is_day"][i])
        hourly.append({"label": "Now" if i == start else _hour_label(hw["time"][i]),
                       "temp": _round(hw["temperature_2m"][i]), "icon": ic,
                       "rain": hw["precipitation_probability"][i] or 0})

    daily = []
    for i in range(len(dw["time"])):
        dl, di = wmo(dw["weather_code"][i], 1)
        d = datetime.fromisoformat(dw["time"][i])
        daily.append({"day": "Today" if i == 0 else d.strftime("%a"), "date": d.strftime("%d %b"),
                      "icon": di, "desc": dl, "lo": _round(dw["temperature_2m_min"][i]),
                      "hi": _round(dw["temperature_2m_max"][i]), "rain": dw["precipitation_probability_max"][i] or 0,
                      "rain_mm": _round(dw["precipitation_sum"][i] or 0, 1)})

    vis = hw["visibility"][start]
    uv = hw["uv_index"][start]
    deg = cur.get("wind_direction_10m")
    return {
        "lat": lat, "lon": lon, "timezone": w.get("timezone"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "observed_at": cur["time"],
        "current": {
            "temp": _round(cur["temperature_2m"]), "feels": _round(cur["apparent_temperature"]),
            "desc": label, "icon": icon, "is_day": bool(is_day), "theme": _theme(cur["weather_code"], is_day),
            "hi": daily[0]["hi"], "lo": daily[0]["lo"], "humidity": _round(cur["relative_humidity_2m"]),
            "wind": _round(cur["wind_speed_10m"]), "gust": _round(cur.get("wind_gusts_10m")),
            "wind_deg": deg, "wind_dir": COMPASS[round(deg / 22.5) % 16] if deg is not None else None,
            "pressure": _round(cur.get("pressure_msl")), "cloud": _round(cur.get("cloud_cover")),
            "precip": _round(cur.get("precipitation") or 0, 1),
            "visibility_km": None if vis is None else round(vis / 1000, 1),
            "dew": _round(hw["dew_point_2m"][start]),
            "uv": _round(uv), "uv_label": _uv_label(uv),
        },
        "sun": {"rise": _clock(dw["sunrise"][0]), "set": _clock(dw["sunset"][0])},
        "hourly": hourly, "daily": daily,
        "aqi": _fetch_aqi(lat, lon),
    }


def live_api(request):
    """GET /api/live/?lat=&lon=  (any location on Earth)"""
    try:
        lat, lon = parse_coords(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    key = f"live:{lat}:{lon}"
    data = cache.get(key)
    if data is None:
        try:
            data = build_live(lat, lon)
        except requests.RequestException:
            return JsonResponse({"error": "Weather service is unreachable right now. Try again shortly."}, status=502)
        except Exception as e:
            return JsonResponse({"error": f"Could not build the forecast: {e}"}, status=502)
        cache.set(key, data, LIVE_TTL)
    return JsonResponse(data)


def geocode_api(request):
    """GET /api/geocode/?q=Pune -> up to 6 matching places."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    q = q[:80]
    key = "geocode:" + q.lower()
    results = cache.get(key)
    if results is None:
        try:
            raw = _get(GEOCODE_URL, {"name": q, "count": 6, "language": "en", "format": "json"}).get("results") or []
        except requests.RequestException:
            return JsonResponse({"error": "Search is unavailable right now"}, status=502)
        results = [{"name": r["name"], "region": r.get("admin1") or "", "country": r.get("country") or "",
                    "lat": r["latitude"], "lon": r["longitude"],
                    "label": ", ".join(x for x in (r["name"], r.get("admin1"), r.get("country")) if x)} for r in raw]
        cache.set(key, results, 3600)
    return JsonResponse({"results": results})


def reverse_api(request):
    """GET /api/reverse/?lat=&lon= -> {"label": "Hinjewadi, Pune"}  (falls back to coordinates)."""
    if "lat" not in request.GET or "lon" not in request.GET:
        return JsonResponse({"error": "lat and lon are required"}, status=400)
    try:
        lat, lon = parse_coords(request)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    lat3, lon3 = round(float(request.GET["lat"]), 3), round(float(request.GET["lon"]), 3)
    key = f"reverse:{lat3}:{lon3}"
    label = cache.get(key)
    if label is None:
        try:
            r = requests.get(REVERSE_URL, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"}, timeout=6,
                             params={"lat": lat3, "lon": lon3, "format": "jsonv2", "zoom": 12, "addressdetails": 1})
            r.raise_for_status()
            a = r.json().get("address", {})
            local = a.get("suburb") or a.get("neighbourhood") or a.get("village") or a.get("town")
            city = a.get("city") or a.get("town") or a.get("county") or a.get("state_district")
            parts = [p for p in (local, city if city != local else None, a.get("state") if not city else None) if p]
            label = ", ".join(parts) or a.get("state") or None
        except (requests.RequestException, ValueError):
            label = None
        if label:
            cache.set(key, label, 86400)
    return JsonResponse({"label": label or f"{lat3:.3f}, {lon3:.3f}", "resolved": bool(label)})
