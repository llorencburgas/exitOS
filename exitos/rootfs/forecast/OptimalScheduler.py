import json
import os
import requests


import forecast.ForecasterManager as ForecastManager
import forecast.Solution as Solution
import numpy as np
import sqlDB as db
from datetime import datetime, timedelta
from logging_config import setup_logger
from scipy.optimize import differential_evolution

from abstraction.AbsConsumer import AbsConsumer
from abstraction.AbsEnergySource import AbsEnergySource
from abstraction.AbsGenerator import AbsGenerator

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

        self.consumers = None
        self.generators = None
        self.energy_sources = None

        self.consumption_sensors = None
        self.generation_sensors = None
        self.energy_source_sensors = None

        self.progress = [] #Array with the best cost value on each step

        self.kwargs_for_simulating = {}
        # key arguments for those assets that share a common restriction and
        # one execution effects the others assets execution

    def prepare_data(self, data):
        logger.debug("Preparing data")
        logger.info(data)

        horizon_hours = 24

        all_saved_sensors = database.get_all_saved_sensors_id()
        all_sensors = []
        consumers = {}
        generators = {}
        energy_sources = {}

        for dispositiu in data:
            for entitat in dispositiu["entities"]:
                if entitat['entity_name'] in all_saved_sensors:
                    current_sensor = {'sensor_id': entitat['entity_name'],
                                      'device_id': dispositiu['device_name'],
                                      'sensor_type': database.get_sensors_type([entitat['entity_name'],])[0],
                                      'sensor_state': entitat.get("entity_state", 0) }
                    all_sensors.append(current_sensor)

        for sensor in all_sensors:
            sensor_id = sensor['sensor_id']
            device_id = sensor['device_id']
            sensor_type = sensor['sensor_type']
            state_val = sensor['sensor_state']

            estimated_max_power = state_val #es pot substituir pel forecast si el tinc.

            if sensor_type == "Consum":
                consumer_obj = AbsConsumer(sensor_id)
                consumer_obj.calendar_range = (0, estimated_max_power)
                consumer_obj.active_hours = horizon_hours
                if device_id not in consumers:
                    consumers[device_id] = {}
                consumers[device_id][sensor_id] = consumer_obj

            elif sensor_type == "Generator":
                generator_obj = AbsGenerator(device_id)
                generator_obj.calendar_range = (0, estimated_max_power)
                generator_obj.active_hours = horizon_hours
                if device_id not in generators:
                    generators[device_id] = {}
                generators[device_id][sensor_id] = generator_obj

            elif sensor_type == "EnergySource":
                energy_obj = AbsEnergySource(sensor_id)
                device_ents = [ent for ent  in data if ent['device_name'] == device_id][0]
                min_val = None
                max_val = None
                for ent in device_ents['entities']:
                    if ent['entity_name'].startswith("number"):
                        min_val = ent['entity_attrs']['min']
                        max_val = ent['entity_attrs']['max']
                if min_val is None:
                    min_val = estimated_max_power
                    max_val = estimated_max_power
                # energy_obj.calendar_range = (max_charge, max_discharge)
                energy_obj.min = min_val
                energy_obj.max = max_val

                energy_obj.active_hours = horizon_hours
                if device_id not in energy_sources:
                    energy_sources[device_id] = {}
                energy_sources[device_id][sensor_id] = energy_obj

        return consumers, generators, energy_sources

    def optimize(self, data):
        logger.info("--------------------------RUNNING COST OPTIMIZATION ALGORITHM--------------------------")

        self.consumers, self.generators, self.energy_sources = self.prepare_data(data)

        self.solucio_run = Solution(consumers = self.consumption_sensors, generators = self.generation_sensors, energy_sources = self.energy_sources)
        self.solucio_final = Solution(consumers = self.consumption_sensors, generators = self.generation_sensors, energy_sources = self.energy_sources)
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





