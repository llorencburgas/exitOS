
import forecast.ForecasterManager as ForecastManager
import sqlDB as db
import logging
import sys

from datetime import datetime, timedelta

database = db.sqlDB()
ha_url = database.base_url
bearer_token = database.supervisor_token
headers = {
    "Authorization": f"Bearer {bearer_token}",
    "Content-Type": "application/json",
}

class OptimalScheduler:
    def __init__(self):
        latitude, longitude = database.get_lat_long()
        self.latitude = latitude
        self.longitude = longitude
        self.meteo_data = ForecastManager.obtainmeteoData(latitude, longitude)