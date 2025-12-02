import copy
import requests
import os
import glob
import json

import forecast.Solution as Solution
import sqlDB as db
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from logging_config import setup_logger
from scipy.optimize import differential_evolution

from abstraction.AbsConsumer import AbsConsumer
from abstraction.AbsEnergyStorage import AbsEnergyStorage
from abstraction.AbsGenerator import AbsGenerator
from abstraction.assets.Battery import Battery

logger = setup_logger()

class OptimalScheduler:
    def __init__(self, database: db):

        self.database = database
        self.latitude, self.longitude = database.get_lat_long()

        if self.database.running_in_ha: self.base_filepath = "share/exitos/"
        else: self.base_filepath = "./share/exitos/"

        self.varbound = None
        self.horizon = 24
        self.horizon_min = 1  # 1 = 60 minuts  | 2 = 30 minuts | 4 = 15 minuts
        self.maxiter = 150

        self.global_consumer_id = ""
        self.global_generator_id = ""
        self.global_consumer_forecast = {
            "forecast_data": None,
            "forecast_timestamps": None
        }
        self.global_generator_forecast = {
            "forecast_data": None,
            "forecast_timestamps": None
        }

        self.consumers = {}
        self.generators = {}
        self.energy_storages = {}

        self.electricity_prices = []


    def start_optimization(self, consumer_id, generator_id, horizon, horizon_min):
        self.horizon = horizon
        self.horizon_min = horizon_min

        self.prepare_data_for_optimization()

        self.global_consumer_id = consumer_id
        self.global_generator_id = generator_id

        self.global_consumer_forecast['forecast_data'], self.global_consumer_forecast['forecast_timestamps'] = self.get_sensor_forecast_data(consumer_id)
        self.global_generator_forecast['forecast_data'], self.global_generator_forecast['forecast_timestamps'] = self.get_sensor_forecast_data(generator_id)

        self.varbound = self.configure_varbounds()

        self.electricity_prices = self.get_hourly_electric_prices()

        init_time = datetime.now()
        result = self.__optimize()
        end_time = datetime.now()

        return 0

    def prepare_data_for_optimization(self):
        """

        :return:
        """

        configs_saved = [os.path.basename(f) for f in glob.glob(self.base_filepath + "optimizations/configs/*.json")]
        all_configs = {}

        for config in configs_saved:
            config_path = os.path.join(self.base_filepath, "optimizations/configs", f"{config}")
            with open(config_path, "r",encoding="utf-8") as f:
                current_config = json.load(f)
            # all_configs[config] = current_config

            if current_config['device_category'] == "Consumer":
                to_save_data = {
                    "device_name": current_config['device_name'],
                }
                self.consumers[current_config['device_name']] = to_save_data

            elif current_config['device_category'] == "Generator":
                to_save_data = {
                    "device_name": current_config['device_name'],
                }
                self.generators[current_config['device_name']] = to_save_data

            elif current_config['device_category'] == "EnergyStorage":
                if current_config['friendly_name'] == "Bateria Sonnen":
                    from abstraction.assets.SonnenBattery import SonnenBattery
                    aux_eff = self.database.get_latest_data_from_sensor(current_config['extra_vars']['eficiencia']['sensor_id'])
                    aux_actual_percentage = self.database.get_latest_data_from_sensor(current_config['extra_vars']['percentatge_actual']['sensor_id'])

                    current_energyStorage = SonnenBattery(config = current_config, eff = aux_eff, perc = aux_actual_percentage)
                else:
                    continue


                self.energy_storages[current_config['device_name']] = current_energyStorage
            else:
                logger.debug(f"     ERROR: Dispositiu {current_config} amb categoria {current_config['device_category']}, ignorant.")
                continue

    def get_sensor_forecast_data(self,sensor_id):
        """
        Obté l'últim forecast del sensor i prepara les dades per a l'optimització

        :param sensor_id: id del sensor a preparar
        :param horizon: hores a simular
        :param horizon_min: minuts per hora 1 = 60 minuts  | 2 = 30 minuts | 4 = 15 minuts
        :return:
        """

        sensor_forecast = self.database.get_data_from_latest_forecast_from_sensorid(sensor_id)

        today = datetime.now()
        start_date = datetime(today.year, today.month, today.day, 0,0)
        end_date = start_date + timedelta(hours = self.horizon - 1)
        timestamps = pd.date_range(start=start_date, end=end_date, freq='h')
        hours = []
        for i in range(len(timestamps)): hours.append(timestamps[i].strftime("%Y-%m-%d %H:%M"))

        sensor_data = []

        for hour in hours:
            if hour in sensor_forecast['timestamp'].values:
                row = sensor_forecast[sensor_forecast['timestamp'] == hour]
                sensor_data.append(row['value'].values[0])
            else:
                sensor_data.append(0)

        return sensor_data, timestamps

    def configure_varbounds(self):
        """
        Configura varbounds
        :return:
        """

        varbound = []
        index = 0

        # CONSUMERS
        for consumer in self.consumers.values():
            consumer.vbound_start = index
            for hour in range(self.horizon * self.horizon_min):
                varbound.append([consumer.min, consumer.max])
                index += 1
            consumer.vbound_end = index - 1

        # GENERATORS
        for generator in self.generators.values():
            generator.vbound_start = index
            for hour in range(self.horizon * self.horizon_min):
                varbound.append([generator.min, generator.max])
                index += 1
            generator.vbound_end = index - 1

        # ENERGY STORAGES
        for energy_storage in self.energy_storages.values():
            energy_storage.vbound_start = index
            for hour in range(self.horizon * self.horizon_min):
                varbound.append([energy_storage.min, energy_storage.max])
                index += 1
            energy_storage.vbound_end = index - 1


        return np.array(varbound)

    def __optimize(self):
        logger.info("🦖 - Començant optimització")

        result = differential_evolution(func = self.cost_DE,
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
                                        callback = self.__update_DE_step,
                                        workers = -1
                                        )

        if not self.database.running_in_ha:
            logger.debug(f"     ▫️ Status: {result['message']}")
            logger.debug(f"     ▫️ Total evaluations: {result['nfev']}")
            logger.debug(f"     ▫️ Solution: {result['x']}")
            logger.debug(f"     ▫️ Cost: {result['fun']}")

        return result['x']

    def cost_DE(self, config):
        logger.info("============ COST DE ===============")
        aux = self.__calc_total_balance(config)
        return aux

    def __update_DE_step(self,bounds, convergence):
        pass

    def __calc_total_balance(self,config):

        total_balance = [0] * self.horizon * self.horizon_min
        total_balance, total_cost, bat_states = self.__calc_total_banace_energy(config, total_balance)
        return total_cost

    def __calc_total_banace_consumer(self, config):
        pass

    def __calc_total_banace_generator(self, config):
        pass

    def __calc_total_banace_energy(self, config, total_balance):

        bat_states = {}


        for energy_storage in self.energy_storages.values():
            start = energy_storage.vbound_start
            end = energy_storage.vbound_end

            res_dict = energy_storage.simula(config[start:end], self.horizon, self.horizon_min)

            if len(res_dict['consumption_profile']) < 24: # -- ?? --
                return None

            for hour in range(0, len(total_balance)):
                total_balance[hour] += res_dict['consumption_profile'][hour]


            bat_states[energy_storage.name] = res_dict['schedule']
        return total_balance, res_dict['total_cost'], bat_states






        return current_es['total_cost']



    def get_hourly_electric_prices(self,):
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
        os.remove('omie_price_pred.csv')

        return_prices = []
        aux = 0
        for i in range(self.horizon):
            for j in range(self.horizon_min):
                return_prices.append(hourly_prices[aux])
            aux += 1
            if aux == 24: aux = 0

        return return_prices





# ===================== OLD CODE =============================================
# ============================================================================
# ============================================================================
# ============================================================================







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
            consum_total_hora = (self.consumers[i] +
                                 aux['consumption_profile'][i] -
                                 self.generators[i])  # W

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


