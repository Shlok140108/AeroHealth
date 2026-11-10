from django.urls import path

from . import views

urlpatterns = [
    path("predict-temperature/", views.predict_temperature_view, name="predict-temperature"),
]
