import sys
import os
import logging
import requests


import forecast.ForecasterManager as ForecastManager
from forecast.Solution import Solution as Solution
import abstraction.AbsConsumer as AbsConsumer
import numpy as np
import sqlDB as db
from datetime import datetime, timedelta
from logging_config import setup_logger
from scipy.optimize import differential_evolution


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
        self.varbound = None
        self.maxiter = 30
        self.solucio_final = None
        self.solucio_run = None
        # self.electricity_price = self.__obtainElectricityPrices()

        self.consumption_sensors = database.get_active_sensors_by_type(sensor_type = 'consum')
        self.generation_sensors = database.get_active_sensors_by_type(sensor_type = 'Generator')

        self.progress = [] #Array with the best cost value on each step

    def optimize(self):
        logger.info("--------------------------RUNNING COST OPTIMIZATION ALGORITHM--------------------------")

        self.solucio_run = Solution(consumers = self.consumption_sensors, generators = self.generation_sensors)
        self.solucio_final = Solution(consumers = self.consumption_sensors, generators = self.generation_sensors)
        self.varbound = self.__configureBounds()

        start_time = datetime.now()
        result = self.__runDEModel(self.costDE)
        end_time = datetime.now()

        return result

    def obtainElectricityPrices(self):
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
        if response.status_code != "200":
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
        os.remove('omie_price_pred.csv')
        return hourly_prices

    def costDE(self, config):
        """Funció de cost on s'optimitza totes les variables possibles"""


    def __runDEModel(self, function):
        result = differential_evolution(
            func = function,
            popsize = 150,
            bounds = self.varbound,
            integrality = [True] * len(self.varbound),
            maxiter = self.maxiter,
            mutation = (0.15, 0.25),
            recombination = 0.7,
            tol = 0.0001,
            strategy = 'best1bin',
            init = 'halton',
            disp = True,
            callback = self.__updateDEStep,
            workers = -1
        )

        logger.debug(f"Status: {result['message']}")
        logger.debug(f"Total Evaluations: {result['nfev']}")
        logger.debug(f"Solution: {result['x']}")
        logger.debug(f"Cost: {result['fun']}")

        return result

    def __configureBounds(self):
        varbound = []
        index = 0

        consumer : AbsConsumer
        for consumer in self.solucio_run.consumers:
            consumer.vbound_start = index

            for hour in range(0, consumer.active_hours):
                varbound.append([consumer.calendar_range[0], consumer.calendar_range[1]])
                index += 1
            consumer.vbound_end = index

        return np.array(varbound)

    def __updateDEStep(self, bounds, convergence):
        pass





