from django.urls import path
from . import api, live, views

urlpatterns = [
    path("", views.overview, name="overview"),
    path("weather/", views.weather_page, name="weather"),
    path("prediction/", views.prediction, name="prediction"),
    path("account/", views.account, name="account"),
    path("login/", views.login_page, name="login"),
    path("signed-out/", views.signed_out, name="signed-out"),
    path("api/overview/", api.overview_api, name="overview-api"),
    path("api/prediction/", api.prediction_api, name="prediction-api"),
    path("api/cities/", api.cities_api, name="cities-api"),
    path("api/live/", live.live_api, name="live-api"),
    path("api/geocode/", live.geocode_api, name="geocode-api"),
    path("api/reverse/", live.reverse_api, name="reverse-api"),
]