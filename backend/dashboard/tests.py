"""Dashboard + live weather tests. Upstream HTTP (Open-Meteo, Nominatim) is mocked with
fixtures shaped like the real responses, so the suite runs offline."""
from unittest import mock

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from weather.ml_service import predict_aqi, predict_aqi_batch

DAYS = [f"2026-11-{10 + d}" for d in range(7)]


def hours(n_days):
    return [f"{DAYS[d]}T{h:02d}:00" for d in range(n_days) for h in range(24)]


def forecast_fixture(code=2):
    t = hours(7)
    n = len(t)
    return {
        "timezone": "Asia/Kolkata",
        "current": {"time": "2026-11-10T14:15", "temperature_2m": 31.4, "relative_humidity_2m": 52,
                    "apparent_temperature": 33.0, "is_day": 1, "precipitation": 0.0, "weather_code": code,
                    "cloud_cover": 40, "pressure_msl": 1009.6, "wind_speed_10m": 11.2,
                    "wind_direction_10m": 250, "wind_gusts_10m": 22.0},
        "hourly": {"time": t, "temperature_2m": [25 + (i % 24) / 3 for i in range(n)],
                   "precipitation_probability": [70 if i % 24 == 18 else 5 for i in range(n)],
                   "weather_code": [code] * n, "is_day": [1 if 6 <= i % 24 <= 18 else 0 for i in range(n)],
                   "visibility": [10000] * n, "dew_point_2m": [18.2] * n, "uv_index": [6.4] * n},
        "daily": {"time": DAYS, "weather_code": [code] * 7, "temperature_2m_max": [32 + d for d in range(7)],
                  "temperature_2m_min": [20] * 7, "precipitation_probability_max": [10, 20, 30, 40, 50, 60, 70],
                  "precipitation_sum": [0.0, None, 1.2, 0, 0, 0, 3.4],
                  "sunrise": [f"{d}T06:40" for d in DAYS], "sunset": [f"{d}T18:05" for d in DAYS],
                  "uv_index_max": [7.1] * 7},
    }


def air_fixture(days=2):
    t = hours(days)
    n = len(t)
    return {"hourly": {"time": t, "pm10": [120.0] * n, "pm2_5": [60.0 + i % 24 for i in range(n)],
                       "carbon_monoxide": [400.0] * n, "nitrogen_dioxide": [30.0] * n,
                       "sulphur_dioxide": [8.0] * n, "ozone": [45.0] * n},
            "current": {"time": "2026-11-10T14:15", "us_aqi": 151, "pm10": 120.0, "pm2_5": 70.0,
                        "carbon_monoxide": 400.0, "nitrogen_dioxide": 30.0, "sulphur_dioxide": 8.0, "ozone": 45.0}}


class Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self): return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def fake_get(url, params=None, **kw):
    if "air-quality-api" in url:
        return Resp(air_fixture(params.get("forecast_days", 2) if params and "hourly" in params else 2))
    if "geocoding-api" in url:
        return Resp({"results": [{"name": "Pune", "admin1": "Maharashtra", "country": "India",
                                  "latitude": 18.51957, "longitude": 73.85535}]})
    if "nominatim" in url:
        return Resp({"address": {"suburb": "Hinjewadi", "city": "Pune", "state": "Maharashtra"}})
    return Resp(forecast_fixture())


class Base(TestCase):
    def setUp(self):
        cache.clear()
        p = mock.patch("requests.get", side_effect=fake_get)
        self.get = p.start()
        self.addCleanup(p.stop)


class ModelTests(SimpleTestCase):
    def test_batch_returns_clipped_floats(self):
        nan = float("nan")
        row = dict(zip(["PM2.5", "PM10", "NO", "NO2", "NOx", "NH3", "CO", "SO2", "O3", "Benzene", "Toluene",
                        "lat", "lon", "month", "Day_of_week"],
                       [60, 120, nan, 30, nan, nan, 0.4, 8, 45, nan, nan, 18.5, 73.8, 11, 1]))
        out = predict_aqi_batch([row, row])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(isinstance(v, float) and 0 <= v <= 500 for v in out))
        self.assertEqual(predict_aqi_batch([]), [])

    def test_single_predict_derives_month_and_weekday_from_date(self):
        from datetime import datetime
        nan = float("nan")
        v = predict_aqi(60, 120, nan, 30, nan, nan, 0.4, 8, 45, nan, nan, 18.5, 73.8, date=datetime(2026, 11, 10))
        self.assertIsInstance(v, float)


class OverviewTests(Base):
    def test_overview_ok(self):
        r = self.client.get("/api/overview/", {"lat": 18.52, "lon": 73.85, "place": "Pune"})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(d["place"], "Pune")
        self.assertEqual(len(d["hourly"]), 8)
        self.assertEqual(len(d["curve"]), 12)
        self.assertEqual(len(d["week"]), 7)
        self.assertTrue(0 <= d["aqi"]["value"] <= 500)
        self.assertRegex(d["rain"], r"^\d+\.\d mm today$")

    def test_null_precip_sum_does_not_crash(self):
        # fixture has None in precipitation_sum[1]; today's value is fine, but make today's None too
        f = forecast_fixture(); f["daily"]["precipitation_sum"][0] = None
        with mock.patch("requests.get", side_effect=lambda u, params=None, **k: Resp(f) if "air-quality" not in u else fake_get(u, params)):
            r = self.client.get("/api/overview/", {"lat": 18.52, "lon": 73.85})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["rain"], "0.0 mm today")

    def test_bad_coords_400(self):
        for q in ({"lat": "abc", "lon": "1"}, {"lat": "nan", "lon": "77"}, {"lat": 95, "lon": 77},
                  {"lat": 51.5, "lon": -0.12}):          # last one: valid but outside India for the AQI model
            self.assertEqual(self.client.get("/api/overview/", q).status_code, 400, q)

    def test_upstream_failure_is_502(self):
        self.get.side_effect = requests.ConnectionError("down")
        self.assertEqual(self.client.get("/api/overview/", {"lat": 18.5, "lon": 73.8}).status_code, 502)


class PredictionTests(Base):
    def test_prediction_ok(self):
        r = self.client.get("/api/prediction/", {"lat": 18.52, "lon": 73.85})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(len(d["days"]), 7)
        self.assertIsNotNone(d["days"][0]["aqi_max"])
        self.assertIn("band", d["advice"])
        self.assertIsNotNone(d["typical_temp_today"])

    def test_outside_india_400(self):
        self.assertEqual(self.client.get("/api/prediction/", {"lat": 40.7, "lon": -74}).status_code, 400)


class LiveTests(Base):
    def test_live_shape(self):
        r = self.client.get("/api/live/", {"lat": 18.5204, "lon": 73.8567})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        c = d["current"]
        self.assertEqual((c["temp"], c["feels"], c["humidity"]), (31, 33, 52))
        self.assertEqual(c["wind_dir"], "WSW")
        self.assertEqual(c["desc"], "Partly cloudy")
        self.assertEqual(c["visibility_km"], 10.0)
        self.assertEqual(len(d["hourly"]), 24)
        self.assertEqual(d["hourly"][0]["label"], "Now")
        self.assertEqual(d["hourly"][1]["label"], "3 PM")         # current time is 14:15
        self.assertEqual(len(d["daily"]), 7)
        self.assertEqual(d["daily"][0]["day"], "Today")
        self.assertEqual(d["sun"], {"rise": "6:40 AM", "set": "6:05 PM"})
        self.assertEqual(d["aqi"]["us_aqi"], 151)
        self.assertTrue(0 <= d["aqi"]["cpcb"] <= 500)               # Indian location -> model estimate

    def test_outside_india_has_no_cpcb_estimate_but_works(self):
        r = self.client.get("/api/live/", {"lat": 51.5, "lon": -0.12})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["aqi"]["cpcb"])

    def test_air_api_down_still_returns_weather(self):
        def flaky(url, params=None, **k):
            if "air-quality" in url: raise requests.ConnectionError("down")
            return fake_get(url, params)
        self.get.side_effect = flaky
        r = self.client.get("/api/live/", {"lat": 18.5, "lon": 73.8})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["aqi"])

    def test_weather_down_is_502_with_message(self):
        self.get.side_effect = requests.ConnectionError("down")
        r = self.client.get("/api/live/", {"lat": 18.5, "lon": 73.8})
        self.assertEqual(r.status_code, 502)
        self.assertIn("unreachable", r.json()["error"])

    def test_validation(self):
        for q in ({"lat": "x", "lon": "1"}, {"lat": "inf", "lon": "1"}, {"lat": 91, "lon": 0}, {"lat": 0, "lon": 181}):
            self.assertEqual(self.client.get("/api/live/", q).status_code, 400, q)

    def test_cached_for_nearby_repeat_requests(self):
        self.client.get("/api/live/", {"lat": 18.5204, "lon": 73.8567})
        calls = self.get.call_count
        self.client.get("/api/live/", {"lat": 18.5211, "lon": 73.8571})   # ~100 m away, same 2-dp cell
        self.assertEqual(self.get.call_count, calls)

    def test_night_icon_and_theme(self):
        f = forecast_fixture(code=0); f["current"]["is_day"] = 0
        self.get.side_effect = lambda u, params=None, **k: Resp(f) if "air-quality" not in u else fake_get(u, params)
        c = self.client.get("/api/live/", {"lat": 18.5, "lon": 73.8}).json()["current"]
        self.assertEqual((c["icon"], c["theme"]), ("🌙", "clear-night"))


class GeocodeReverseTests(Base):
    def test_geocode(self):
        r = self.client.get("/api/geocode/", {"q": "Pune"}).json()["results"]
        self.assertEqual(r[0]["label"], "Pune, Maharashtra, India")
        self.assertEqual(r[0]["lat"], 18.51957)

    def test_geocode_short_query_makes_no_upstream_call(self):
        self.assertEqual(self.client.get("/api/geocode/", {"q": "a"}).json(), {"results": []})
        self.get.assert_not_called()

    def test_reverse_label(self):
        d = self.client.get("/api/reverse/", {"lat": 18.5913, "lon": 73.7389}).json()
        self.assertEqual(d, {"label": "Hinjewadi, Pune", "resolved": True})

    def test_reverse_falls_back_to_coordinates(self):
        self.get.side_effect = requests.ConnectionError("blocked")
        d = self.client.get("/api/reverse/", {"lat": 18.5913, "lon": 73.7389}).json()
        self.assertEqual(d, {"label": "18.591, 73.739", "resolved": False})

    def test_reverse_requires_coords(self):
        self.assertEqual(self.client.get("/api/reverse/").status_code, 400)

    def test_reverse_sends_user_agent(self):
        self.client.get("/api/reverse/", {"lat": 18.5913, "lon": 73.7389})
        self.assertIn("AeroHealth", self.get.call_args.kwargs["headers"]["User-Agent"])


class PageTests(Base):
    def test_pages_render(self):
        for path in ("/", "/weather/", "/prediction/", "/account/", "/login/", "/signed-out/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_weather_page_has_tracker_and_live_button(self):
        html = self.client.get("/weather/").content.decode()
        for needle in ("id=\"livebtn\"", "id=\"trk-btn\"", "weather.js", "location.js", "leaflet.js"):
            self.assertIn(needle, html)
