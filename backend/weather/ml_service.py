import os
import pickle
import pandas as pd
from datetime import datetime
from django.conf import settings
from geopy.distance import geodesic

MODELS_DIR = os.path.join(settings.BASE_DIR, "models")
MODELPATH = os.path.join(MODELS_DIR, "aqi_xgboost.pkl")
_model = None
PROPHET_DIR = os.path.join(MODELS_DIR, "prophet_cities")

_xgb_temp_model = None
_city_lookup = None
_prophet_cache = {}  # loaded on demand, cached after first use

NEAR_CITY_THRESHOLD_KM = 30  # if within this distance of a known city, use Prophet instead of XGBoost


def get_xgb_temp_model():
    global _xgb_temp_model
    if _xgb_temp_model is None:
        with open(os.path.join(MODELS_DIR, "temp_xgboost.pkl"), "rb") as f:
            _xgb_temp_model = pickle.load(f)
    return _xgb_temp_model


def get_city_lookup():
    global _city_lookup
    if _city_lookup is None:
        with open(os.path.join(PROPHET_DIR, "city_lookup.pkl"), "rb") as f:
            _city_lookup = pickle.load(f)
    return _city_lookup


def get_prophet_model(city_name):
    if city_name not in _prophet_cache:
        path = os.path.join(PROPHET_DIR, f"{city_name}.pkl")
        with open(path, "rb") as f:
            _prophet_cache[city_name] = pickle.load(f)
    return _prophet_cache[city_name]


def find_nearby_city(lat, lon):
    """Returns the closest known city if within threshold distance, else None."""
    lookup = get_city_lookup()
    closest_city, closest_dist = None, float("inf")

    for city, coords in lookup.items():
        dist = geodesic((lat, lon), (coords["lat"], coords["lon"])).km
        if dist < closest_dist:
            closest_city, closest_dist = city, dist

    if closest_dist <= NEAR_CITY_THRESHOLD_KM:
        return closest_city
    return None


def predict_temperature(lat, lon, date=None):
    if date is None:
        date = datetime.now()

    nearby_city = find_nearby_city(lat, lon)

    if nearby_city:
        model = get_prophet_model(nearby_city)
        future = pd.DataFrame({"ds": [pd.Timestamp(date)]})
        forecast = model.predict(future)
        predicted_temp = float(forecast["yhat"].iloc[0])
        return predicted_temp, "prophet", nearby_city

    else:
        model = get_xgb_temp_model()
        features = pd.DataFrame([{
            "lat": lat, "lon": lon,
            "month": date.month, "day_of_year": date.timetuple().tm_yday,
        }])
        predicted_temp = float(model.predict(features)[0])
        return predicted_temp, "xgboost", None


def get_model():
    global _model
    if _model is None:
        with open(MODELPATH, "rb") as f:
            _model = pickle.load(f)
    return _model


AQI_FEATURES = ["PM2.5", "PM10", "NO", "NO2", "NOx", "NH3", "CO", "SO2", "O3",
                "Benzene", "Toluene", "lat", "lon", "month", "Day_of_week"]


def predict_aqi_batch(rows):
    """rows: list of dicts keyed by AQI_FEATURES (missing pollutants may be NaN).
    Returns one CPCB-scale AQI (float, clipped to 0-500) per row, in order."""
    if not rows:
        return []
    frame = pd.DataFrame(rows, columns=AQI_FEATURES).astype(float)
    preds = get_model().predict(frame)
    return [float(min(max(p, 0.0), 500.0)) for p in preds]


def predict_aqi(pm25, pm10, no, no2, nox, nh3, co, so2, o3,
                benzene, toluene, lat, lon, month=None, day_of_week=None, date=None):
    """Single AQI estimate. month / day_of_week default to the given date (or now);
    day_of_week uses Monday=0 like the training data."""
    if date is None:
        date = datetime.now()
    row = dict(zip(AQI_FEATURES, [
        pm25, pm10, no, no2, nox, nh3, co, so2, o3, benzene, toluene, lat, lon,
        date.month if month is None else month,
        date.weekday() if day_of_week is None else day_of_week,
    ]))
    return predict_aqi_batch([row])[0]
