from rest_framework.test import APITestCase

URL = "/api/weather/predict-temperature/"


class PredictTemperatureTests(APITestCase):
    def test_near_known_city_uses_prophet(self):
        r = self.client.post(URL, {"lat": 18.52, "lon": 73.85, "date": "2026-11-15"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["model_used"], "prophet")
        self.assertEqual(r.data["matched_city"], "Pune")

    def test_far_from_cities_uses_xgboost(self):
        r = self.client.post(URL, {"lat": 20.0, "lon": 78.0, "date": "2026-11-15"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["model_used"], "xgboost")
        self.assertIsNone(r.data["matched_city"])

    def test_missing_lat_lon_returns_400(self):
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 400)

    def test_outside_india_returns_400(self):
        r = self.client.post(URL, {"lat": 51.5, "lon": -0.12}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_bad_date_returns_400(self):
        r = self.client.post(URL, {"lat": 18.5, "lon": 73.8, "date": "tomorrow"}, format="json")
        self.assertEqual(r.status_code, 400)
