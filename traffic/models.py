from django.db import models

# Create your models here.
from django.db import models

class Prediction(models.Model):
    location    = models.CharField(max_length=100, default="Lagos")
    latitude    = models.FloatField(null=True, blank=True)
    longitude   = models.FloatField(null=True, blank=True)
    level       = models.CharField(max_length=20)
    weather     = models.CharField(max_length=50, default="cloudy")
    speed       = models.FloatField(default=0)
    travel_time = models.FloatField(default=0)
    road_length = models.FloatField(default=0)
    forecast    = models.CharField(max_length=50, default="Now")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.location} — {self.level} ({self.created_at})"


class AdminUser(models.Model):
    username       = models.CharField(max_length=50, unique=True)
    password_hash  = models.CharField(max_length=256)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username