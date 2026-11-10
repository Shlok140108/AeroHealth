#!/usr/bin/env bash
# Demo for the showcase. Start the server first:  python manage.py runserver
URL=http://127.0.0.1:8000/api/weather/predict-temperature/

echo "1) Near Pune -> should use Prophet (city-specific model)"
curl -s -X POST $URL -H "Content-Type: application/json" -d '{"lat": 18.52, "lon": 73.85, "date": "2026-11-15"}'
echo; echo
echo "2) Rural Maharashtra, far from any known city -> should use XGBoost fallback"
curl -s -X POST $URL -H "Content-Type: application/json" -d '{"lat": 20.0, "lon": 78.0, "date": "2026-11-15"}'
echo; echo
echo "3) Invalid input -> should return a clear error"
curl -s -X POST $URL -H "Content-Type: application/json" -d '{"lat": "abc"}'
echo
