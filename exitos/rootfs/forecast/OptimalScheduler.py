import requests


import forecast.ForecasterManager as ForecastManager
import forecast.Solution as Solution
import numpy as np
import pandas as pd
import sqlDB as db
from datetime import datetime, timedelta
from logging_config import setup_logger
from scipy.optimize import differential_evolution

from abstraction.AbsConsumer import AbsConsumer
from abstraction.AbsEnergySource import AbsEnergySource
from abstraction.AbsGenerator import AbsGenerator
from assets.Battery import Battery


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
        self.varbound = None

        self.maxiter = 30
        self.hores_simular = 24
        self.minuts = 1
        self.timestamps = None
        self.solucio_final = None
        self.solucio_run = None

        self.consumers = None
        self.generators = None
        self.energy_sources = None

        self.preu_llum_horari = self.get_hourly_electric_prices()

        self.progress = [] #Array with the best cost value on each step

        self.kwargs_for_simulating = {}
        # key arguments for those assets that share a common restriction and
        # one execution effects the others assets execution


        # !!!! CANVIAR PER FUNCIÓ QUE OBTÉ ELS PREUS REALS MÉS ENDAVANT !!!!

    def prepare_data(self, data):
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

                sensor_forecast = database.get_data_from_latest_forecast(sensor_id+".pkl")

                logger.warning("forecast obtingut")
                logger.debug(sensor_forecast)

                consumer_obj.calendar_range = (0, estimated_max_power)
                consumer_obj.active_hours = horizon_hours
                consumer_obj.active_calendar = [0, horizon_hours-1]
                if device_id not in consumers:
                    consumers[device_id] = {}
                consumers[device_id][sensor_id] = consumer_obj

            elif sensor_type == "Generator":
                generator_obj = AbsGenerator(device_id)
                generator_obj.calendar_range = (0, estimated_max_power)
                generator_obj.active_hours = horizon_hours
                generator_obj.active_calendar = [0, horizon_hours-1]
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
                energy_obj.active_calendar = [0, horizon_hours-1]

                if device_id not in energy_sources:
                    energy_sources[device_id] = {}
                energy_sources[device_id][sensor_id] = energy_obj

        return consumers, generators, energy_sources

    def optimize(self, consumer, generator, energy_source:Battery, hores_simular, minuts, timestamps):
        logger.info("🦖 - Començant optimització")

        self.consumers = consumer
        self.generators = generator
        self.energy_sources = energy_source
        self.hores_simular = hores_simular
        self.minuts = minuts
        self.timestamps = timestamps
        consum_bateria = self.energy_sources.simula()
        self.varbound = (
                # [(min(consum_bateria['perfil_consum']), max(consum_bateria['perfil_consum']))] * 24   # 24 hores per a l’energy source
            [(0,100)] * 24
        )

        result = self.__runDEModel(self.costDE)
        return result

    def __runDEModel(self, function):
        result = differential_evolution(func = function,
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
                                        updating = 'deferred',
                                        # callback = self.__updateDEStep,
                                        workers = -1
                                        )

        logger.debug(f"     ▫️ Status: {result['message']}")
        logger.debug(f"     ▫️ Total evaluations: {result['nfev']}")
        logger.debug(f"     ▫️ Solution: {result['x']}")
        logger.debug(f"     ▫️ Cost: {result['fun']}")

        return result

    def costDE(self, config):
        preu_llum_horari = self.preu_llum_horari
        self.energy_sources.simula(config)

        resultat_total = 0
        # logger.warning(f"{'HORA':<20} {'CARREGA':<13} {'CAPACITAT': <13} {'PV':<8} {'CONSUM_LAB':<15} {'CONSUM_TOTAL':<15} {'PREU_LLUM':<12} {'PREU_VENTA':<12}")
        for i in range(0, self.hores_simular * self.minuts):
            consum_total_hora = self.consumers[i] + self.energy_sources.perfil_consum[i] - self.generators[i]  # W

            preu_venta = (preu_llum_horari[i] / 1000) * consum_total_hora  # W
            resultat_total += preu_venta

            # if i % 2 == 0:
            #     logger.debug(
            #         f"{self.timestamps[i]:<20} {self.energy_sources.perfil_consum[i]:<13.4f} {self.energy_sources.capacitat_actual[i]:<13.2f} {self.generators[i]:<8.2f} {self.consumers[i]:<15.2f} {consum_total_hora:<15.2f} {preu_llum_horari[i]:<12.2f} {preu_venta:<12.2f}")
            # else:
            #     logger.info(
                    # f"{self.timestamps[i]:<20} {self.energy_sources.perfil_consum[i]:<13.4f} {self.energy_sources.capacitat_actual[i]:<13.2f} {self.generators[i]:<8.2f} {self.consumers[i]:<15.2f} {consum_total_hora:<15.2f} {preu_llum_horari[i]:<12.2f} {preu_venta:<12.2f}")
        # logger.critical(f"Preu final: {round(resultat_total, 3)} €")
        return resultat_total


    def get_hourly_electric_prices(self, hores_simular: int = 24, minuts: int = 1):
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



    #
    # def __calcConsumersBalance(self, config):
    #     self.kwargs_for_simulating.clear()
    #
    #     total_profile = [0] * self.hores_simular #perfil total de comsum hora a hora
    #     individual_profile = {} # diccionari amb key = nom del consumer i valor = consumption profile
    #     total_kwh = 0 # total de kwh gastats
    #     total_hidrogen_kg = 0
    #
    #     total_cost = 0
    #     valid_consumers = 0
    #
    #
    #     consumer_sensor: AbsConsumer
    #     for consumer in self.solucio_run.consumers.values():
    #         for consumer_sensor in consumer.values():
    #             start = consumer_sensor.active_calendar[0]
    #             end = consumer_sensor.active_calendar[1] + 1
    #
    #             self.kwargs_for_simulating['electricity_prices'] = self.electricity_prices[start:end]
    #
    #             res_dictionary = consumer_sensor.doSimula(calendar = config[consumer_sensor.vbound_start:consumer_sensor.vbound_end],
    #                                                       kwargs_simulation = self.kwargs_for_simulating)
    #
    #             consumption_profile, consumed_Kwh, total_hidrogen_kg, cost = self.__unpackSimulationResults(res_dictionary)
    #
    #
    #         logger.debug("DEBUG POINT")
    #
    # def __calcBalanc(self, config):
    #     # cost de tots els consumers
    #     consumers_total_profile, consumers_individual_profile, consumers_total_kwh, valid_ones, \
    #         cost_aproximacio, total_hidrogen_kg = self.__calcConsumersBalance(config)
    #
    # def costDE(self, config):
    #     """Funció de cost on s'optimitza totes les variables possibles"""
    #     balanc_energetic_per_hores, cost, total_hidrogen_kg, numero_assets_ok, \
    #         consumers_individual_profile, generators_individual_profile, es_states = self.__calcBalanc(config)
    #
    # def __runDEModel(self, function):
    #     self.costDE("")
    #     result = differential_evolution(
    #         func = function,
    #         popsize = 150,
    #         bounds = self.varbound,
    #         integrality = [True] * len(self.varbound),
    #         maxiter = self.maxiter,
    #         mutation = (0.15, 0.25),
    #         recombination = 0.7,
    #         tol = 0.0001,
    #         strategy = 'best1bin',
    #         init = 'halton',
    #         disp = True,
    #         callback = self.__updateDEStep,
    #         workers = -1
    #     )
    #
    #     logger.debug(f"Status: {result['message']}")
    #     logger.debug(f"Total Evaluations: {result['nfev']}")
    #     logger.debug(f"Solution: {result['x']}")
    #     logger.debug(f"Cost: {result['fun']}")
    #
    #     return result
    #
    # def __configureBounds(self):
    #     varbound = []
    #     index = 0
    #
    #     if self.solucio_run.consumers:
    #         for consumer in self.solucio_run.consumers.values():
    #             for consumer_sensor in consumer.values():
    #                 consumer_sensor.vbound_start = index
    #
    #                 for hour in range(0, consumer_sensor.active_hours):
    #                     varbound.append([consumer_sensor.calendar_range[0], consumer_sensor.calendar_range[1]])
    #                     index += 1
    #                 consumer_sensor.vbound_end = index
    #
    #     if self.solucio_run.energy_sources:
    #         for energy_source in self.solucio_run.energy_sources.values():
    #             for energy_source_sensor in energy_source.values():
    #                 energy_source_sensor.vbound_start = index
    #
    #                 max_discharge = energy_source_sensor.min
    #                 max_charge = energy_source_sensor.max
    #
    #                 for hour in range(0, energy_source_sensor.active_hours):
    #                     varbound.append([max_discharge, max_charge])
    #                     index += 1
    #                 energy_source_sensor.vbound_end = index
    #
    #     return np.array(varbound)
    #
    # def __updateDEStep(self, bounds, convergence):
    #     pass





