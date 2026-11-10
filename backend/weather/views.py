from datetime import datetime

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .ml_service import predict_temperature

# Rough bounding box for India (keeps the demo honest: models were trained on Indian data)
INDIA_LAT = (6.0, 37.5)
INDIA_LON = (68.0, 98.0)


@api_view(["POST"])
def predict_temperature_view(request):
    """
    POST /api/weather/predict-temperature/
    Body: {"lat": float, "lon": float, "date": "YYYY-MM-DD" (optional)}
    """
    try:
        lat = float(request.data.get("lat"))
        lon = float(request.data.get("lon"))
    except (TypeError, ValueError):
        return Response({"error": "lat and lon are required and must be numbers"},
                        status=status.HTTP_400_BAD_REQUEST)

    if not (INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]):
        return Response({"error": "Location is outside India; the models were trained on Indian data"},
                        status=status.HTTP_400_BAD_REQUEST)

    date = None
    date_str = request.data.get("date")
    if date_str:
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            return Response({"error": "date must be ISO format, e.g. 2026-11-15"},
                            status=status.HTTP_400_BAD_REQUEST)

    predicted_temp, source, city = predict_temperature(lat, lon, date)

    return Response({
        "predicted_temperature": round(predicted_temp, 1),
        "model_used": source,      # "prophet" (near a known city) or "xgboost" (national fallback)
        "matched_city": city,
    })
