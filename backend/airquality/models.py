from django.db import models


class Location(models.Model):
    name = models.CharField(max_length=200)
    lat = models.FloatField()
    lon = models.FloatField()
    state = models.CharField(max_length=100, blank=True)
    is_cpcb_station = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
