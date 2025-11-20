import copy
import requests
import os
import glob
import json

import forecast.Solution as Solution
import sqlDB as db
from datetime import datetime, timedelta
from logging_config import setup_logger
from scipy.optimize import differential_evolution

from abstraction.AbsConsumer import AbsConsumer
from abstraction.AbsEnergySource import AbsEnergySource
from abstraction.AbsGenerator import AbsGenerator
from abstraction.assets.Battery import Battery

from pathlib import Path
from configparser import ConfigParser


logger = setup_logger()

class OptimalScheduler:
    def __init__(self, database: db):

        self.database = database
        self.latitude, self.longitude = database.get_lat_long()

        self.varbound = None

        self.maxiter = 300
        self.hores_simular = 24
        self.minuts = 1
        self.timestamps = None
        self.solucio_final = Solution.Solution()
        self.solucio_run = Solution.Solution()

        self.consumers = None
        self.generators = None
        self.energy_sources = None

        self.preu_llum_horari = self.get_hourly_electric_prices()

        self.progress = [] #Array with the best cost value on each step

        self.kwargs_for_simulating = {}


    def optimize2(self, consumer, generator, energy_source:Battery, hores_simular, minuts, timestamps):
        logger.info("🦖 - Començant optimització")

        self.consumers = consumer
        self.generators = generator
        self.energy_sources = energy_source
        self.hores_simular = hores_simular
        self.minuts = minuts
        self.timestamps = timestamps
        # consum_bateria = self.energy_sources.simula()
        self.solucio_run.consumidors = consumer
        self.solucio_run.generadors = generator
        self.varbound = (
                # [(min(consum_bateria['perfil_consum']), max(consum_bateria['perfil_consum']))] * 24   # 24 hores per a l’energy source
            [(-2.5,2.5)] * 24
        )

        result = self.__runDEModel(self.costDE)
        return result

    def optimize(self, global_consumer_id, global_generator_id):
        logger.info("🦖 - Començant optimització")

        logger.debug(f" CONSUM: {global_consumer_id} \n GENERACIÓ: {global_generator_id}")
        forecast_consum = self.database.get_data_from_latest_forecast_from_sensorid(global_consumer_id)
        forecast_generator = self.database.get_data_from_latest_forecast_from_sensorid(global_generator_id)

        config_path = os.path.join(self.database.base_filepath, "optimizations/configs/*.json")
        all_devices = {}
        for file_path in glob.glob(config_path):
            with open(file_path, "r", encoding="utf-8") as f:
                device_config = json.load(f)
                device_name = device_config["device_name"]
                all_devices[device_name] = device_config


        for device in all_devices:
            if device['device_type'] == "bateria":
                energy_source = Battery(hours_to_simulate = 24,
                                        minutes_per_hour = 1,
                                        max_capacity = device['restrictions']['Capacitat màxima (kWh)'],
                                        min_capacity = device['restrictions']['Capacitat mínima (kWh)'],
                                        actual_percentage = 0,  #LLEGIR L'ÚLTIM VALOR DEL SENSOR
                                        efficiency = 100) #LLEGIR L'ÚLTIM VALOR DEL SENSOR
            i=0





    def __runDEModel(self, function):
        result = differential_evolution(func = function,
                                        popsize = 100,
                                        bounds = self.varbound,
                                        integrality = [True] * len(self.varbound),
                                        maxiter = self.maxiter,
                                        mutation = (0.15, 0.25),
                                        recombination = 0.7,
                                        tol = 0.0001,
                                        strategy = 'best1bin',
                                        init = 'halton',
                                        disp = True,
                                        updating = 'deferred',
                                        callback = self.__updateDEStep,
                                        workers = 1
                                        )

        if not self.database.running_in_ha:
            logger.debug(f"     ▫️ Status: {result['message']}")
            logger.debug(f"     ▫️ Total evaluations: {result['nfev']}")
            logger.debug(f"     ▫️ Solution: {result['x']}")
            logger.debug(f"     ▫️ Cost: {result['fun']}")

        return result

    def costDE(self, config):
        preu_llum_horari = self.preu_llum_horari
        aux = self.energy_sources.simula_kw(config)
        self.solucio_run.consum_hora = []
        self.solucio_run.preu_venta_hora = []

        resultat_total = 0
        for i in range(0, self.hores_simular * self.minuts):
            consum_total_hora = self.consumers[i] + aux['consumption_profile'][i] - self.generators[i]  # W

            preu_venta = (preu_llum_horari[i] / 1000) * consum_total_hora  # W
            resultat_total += preu_venta

            self.solucio_run.consum_hora.append(consum_total_hora)
            self.solucio_run.preu_venta_hora.append(preu_venta)

        self.solucio_run.preu_llum_horari = preu_llum_horari
        self.solucio_run.preu_total = resultat_total
        self.solucio_run.timestamps = self.timestamps
        self.solucio_run.perfil_consum_energy_source = aux['consumption_profile']
        self.solucio_run.capacitat_actual_energy_source = aux['consumed_Kwh']
        self.solucio_run.soc_objectiu = aux['soc_objectiu']


        return resultat_total

    def __updateDEStep(self, bounds, convergence):
        self.solucio_final = copy.deepcopy(self.solucio_run)
        if not self.database.running_in_ha:
            logger.debug(f"     Cost aproximacio {self.solucio_run.preu_total}")

    @staticmethod
    def get_hourly_electric_prices(hores_simular: int = 24, minuts: int = 1):
        today = datetime.today().strftime('%Y%m%d')
        url = f"https://www.omie.es/es/file-download?parents%5B0%5D=marginalpdbc&filename=marginalpdbc_{today}.1"
        response = requests.get(url)

        if response.status_code != 200:
            logger.error(f"❌ No s'ha pogut obtenir el preu de la llum de OMIE: {response.status_code}.")
            return -1

        with open('omie_price_pred.csv', "wb") as file:
            file.write(response.content)

        hourly_prices = []
        with open('omie_price_pred.csv', "r") as file:
            for line in file.readlines()[1:-1]:
                components = line.strip().split(';')
                components.pop(-1)
                hourly_price = float(components[-1])
                hourly_prices.append(hourly_price)
        # os.remove('omie_price_pred.csv')

        return_prices = []
        aux = 0
        for i in range(hores_simular):
            for j in range(minuts):
                return_prices.append(hourly_prices[aux])
            aux += 1
            if aux == 24: aux = 0

        return return_prices
