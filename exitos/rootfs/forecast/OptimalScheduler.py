import sys
import os
import logging
import requests


import forecast.ForecasterManager as ForecastManager
import sqlDB as db
from datetime import datetime, timedelta
from logging_config import setup_logger




logger = setup_logger()
database = db.SqlDB()
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
        # self.electricity_price = self.__obtainElectricityPrices()


    def __obtainElectricityPrices(self):
        """
        Fetches the hourly electricity prices for buying from the OMIE API.
        If the next day's data is unavaliable, today's data is fetched.

        Returns
        -----------
        hourly_prices : list
            List of hourly electricity prices for buying.
        """
        tomorrow = datetime.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y%m%d')

        url = f"https://www.omie.es/es/file-download?parents%5B0%5D=marginalpdbc&filename=marginalpdbc_{tomorrow_str}.1"
        response  = requests.get(url)

        # If tomorrow's prices are unavailable, fallback to today's data
        if response.status_code != 200:
            logger.debug(f"Request failed with status code {response.status_code}. Fetching data from today")
            today = datetime.today().strftime('%Y%m%d')
            url = f"https://www.omie.es/es/file-download?parents%5B0%5D=marginalpdbc&filename=marginalpdbc_{today}.1"
            response = requests.get(url)

        #Save the retrieved data into a CSV file
        with open("omie_price_pred.csv", 'wb') as f:
            f.write(response.content)

        # Parse the CSV to extract hourly prices
        hourly_prices = []
        with open('omie_price_pred.csv', 'r') as file:
            for line in file.readlines()[1:-1]:
                components = line.strip().split(';')
                components.pop(-1)  # Remove trailing blank entry
                hourly_price = float(components[-1])
                hourly_prices.append(hourly_price)

        return hourly_prices