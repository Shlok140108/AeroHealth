from rest_framework import serializers
from .models import AQIForecast

class AQIForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = AQIForecast
        fields = ['location','prediction','forecast_for','generated_at','confidence_lower','confidence_upper','model_version']

class PredictionRequestSerializer(serializers.Serializer):
    pm25 = serializers.FloatField()
    pm10 = serializers.FloatField()
    no = serializers.FloatField()
    no2 = serializers.FloatField()
    nox = serializers.FloatField()
    nh3 = serializers.FloatField()
    co = serializers.FloatField()
    so2 = serializers.FloatField()
    o3 = serializers.FloatField()
    benzene = serializers.FloatField()
    toluene = serializers.FloatField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)