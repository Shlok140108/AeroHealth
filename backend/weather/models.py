from django.db import models
from airquality.models import Location

class AQIForecast(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    prediction = models.FloatField()
    forecast_for = models.DateTimeField()
    generated_at = models.DateTimeField(auto_now_add=True)
    confidence_lower = models.FloatField(null=True)
    confidence_upper = models.FloatField(null=True)
    model_version = models.CharField(max_length=20)

    class Meta:
        indexes = [models.Index(fields=["location", "forecast_for"])]