import os
import requests


import forecast.ForecasterManager as ForecastManager
from forecast.Solution import Solution as Solution
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
        # self.meteo_data = ForecastManager.obtainmeteoData(latitude, longitude)
        self.varbound = None
        self.maxiter = 30
        self.hores_simular = 24
        self.solucio_final = None
        self.solucio_run = None
        # self.electricity_price = self.__obtainElectricityPrices()

        self.consumption_sensors = database.get_active_sensors_by_type(sensor_type = 'consum')
        self.generation_sensors = database.get_active_sensors_by_type(sensor_type = 'Generator')

        self.progress = [] #Array with the best cost value on each step

        self.kwargs_for_simulating = {}
        # key arguments for those assets that share a common restriction and
        # one execution effects the others assets execution

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

    def __calcConsumersBalance(self, config):
        self.kwargs_for_simulating.clear()

        total_profile = [0] * self.hores_simular #perfil total de comsum hora a hora
        individual_profile = {} # diccionari amb key = nom del consumer i valor = consumption profile
        total_kwh = 0 # total de kwh gastats
        total_hidrogen_kg = 0
        total_cost = 0
        valid_consumers = 0

        for consumer in self.solucio_run.consumers.values():
            start = consumer['active_calendar']


            logger.debug("DEBUG POINT")



    def __calcBalanc(self, config):
        # cost de tots els consumers
        consumers_total_profile, consumers_individual_profile, consumers_total_kwh, valid_ones, \
            cost_aproximacio, total_hidrogen_kg = self.__calcConsumersBalance(config)

    def costDE(self, config):
        """Funció de cost on s'optimitza totes les variables possibles"""
        balanc_energetic_per_hores, cost, total_hidrogen_kg, numero_assets_ok, \
            consumers_individual_profile, generators_individual_profile, es_states = self.__calcBalanc(config)

    def __runDEModel(self, function):
        self.costDE("")
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

        for consumer in self.solucio_run.consumers.values():
            consumer["vbound_start"] = index

            for hour in range(0, consumer["active_hours"]):
                varbound.append([consumer["calendar_range"][0], consumer["calendar_range"][1]])
                index += 1
            consumer["vbound_end"] = index

        return np.array(varbound)

    def __updateDEStep(self, bounds, convergence):
        pass





