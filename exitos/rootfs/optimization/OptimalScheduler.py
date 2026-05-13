import requests
import os
import glob
import json
import logging

import sqlDB as db
import pandas as pd
from datetime import datetime, timedelta
from scipy.optimize import differential_evolution, Bounds


from abstraction.AbsEnergyStorage import AbsEnergyStorage
from abstraction.DeviceRegistry import DEVICE_REGISTRY, create_device_from_config


logger = logging.getLogger("exitOS")

class OptimalScheduler:
    def __init__(self, database: db):
        """
        Controlador central per a l'optimització de recursos energètics en una xarxa local.

        Aquesta classe s'encarrega de gestionar la programació òptima (scheduling) de consumidors,
        generadors i sistemes d'emmagatzematge d'energia (bateries). Utilitza dades de previsió
        de consum i generació, així com els preus de l'electricitat, per resoldre un problema
        d'optimització que minimitzi el cost o maximitzi l'autoconsum en un horitzó temporal definit.

        Atributs principals:
            database: Connexió amb la base de dades o el sistema (e.g., Home Assistant).
            horizon: Finestra temporal de planificació (per defecte 24 hores).
            horizon_min: Resolució temporal de cada interval (pas de temps).
            maxiter: Límit d'iteracions per a l'algorisme d'optimització (ajustat segons l'entorn).
            energy_storages: Diccionari de bateries disponibles per a la gestió de càrrega/descàrrega.
        :param database: Referencia a la classe SqlDB
        """

        self.database = database
        self.latitude, self.longitude = database.get_lat_long()

        if self.database.running_in_ha: self.base_filepath = "share/exitos/"
        else: self.base_filepath = "./share/exitos/"

        self.varbound = None
        self.horizon = 24
        self.horizon_min = 1  # 1 = 60 minuts  | 2 = 30 minuts | 4 = 15 minuts
        self.maxiter = 1500 if database.running_in_ha else 100
        self.timestamps = []

        self.global_consumer_id = ""
        self.global_generator_id = ""
        self.global_consumer_forecast = {
            "forecast_data": [0] * (self.horizon * self.horizon_min),
            "forecast_timestamps": [0] * (self.horizon * self.horizon_min)
        }
        self.global_generator_forecast = {
            "forecast_data": [0] * (self.horizon * self.horizon_min),
            "forecast_timestamps": [0] * (self.horizon * self.horizon_min)
        }

        self.consumers = {}
        self.generators = {}
        self.energy_storages = {}

        self.best_result = 9999
        self.current_result = 0
        self.best_result_balance = None
        self.current_result_balance = None

        self.electricity_prices = []


    def start_optimization(self, consumer_id, generator_id, horizon, horizon_min, today):
        """
        Inicia i coordina el procés d'optimització energètica per a un període determinat.

        Aquest mètode actua com a orquestrador principal: prepara les dades d'entrada, obté les
        previsions de consum i generació per als sensors especificats, configura els límits de les
        variables de decisió (varbounds) i recupera els preus de l'electricitat. Finalment, executa
        l'algorisme d'optimització per trobar la configuració de dispositius que minimitzi el cost,
        calculant el balanç energètic resultant.

        :param consumer_id: Identificador del sensor de consum global.
        :param generator_id: Identificador del sensor de generació (e.g., plaques solars).
        :param horizon: Nombre d'hores de la finestra de planificació.
        :param horizon_min: Resolució temporal (intervals per hora).
        :param today: Data de referència per a l'optimització.
        :return: Una tupla amb: (èxit del procés, configuració per dispositiu, costos, balanç total).
        """
        try:
            self.horizon = horizon
            self.horizon_min = horizon_min

            has_data = self.prepare_data_for_optimization()

            if has_data:
                self.global_consumer_id = consumer_id
                self.global_generator_id = generator_id

                self.global_consumer_forecast['forecast_data'], self.global_consumer_forecast['forecast_timestamps'] = self.get_sensor_forecast_data(consumer_id, today)
                self.global_generator_forecast['forecast_data'], self.global_generator_forecast['forecast_timestamps'] = self.get_sensor_forecast_data(generator_id, today)

                self.varbound = self.configure_varbounds()

                self.electricity_prices = self.get_hourly_electric_prices()

                result, cost = self.__optimize()
                total_balance = self.__calc_total_balance(config = result, total = False)
                all_devices_config = self.get_hourly_config_for_device(result)
            else:
                cost = []
                total_balance = []
                all_devices_config = []

            return has_data, all_devices_config, cost, total_balance

        except Exception as e:
            logger.error(f"❌ No s'ha pogut realitzar l'optimització: {e}")
            return False, None, None, None


    def prepare_data_for_optimization(self):
        """
        Carrega i inicialitza els dispositius des de fitxers de configuració per preparar l'entorn d'optimització.

        Escaneja el directori de configuracions desades, llegeix els fitxers JSON corresponents
        i instancia cada dispositiu utilitzant una fàbrica (factory). Els objectes resultants
        s'organitzen en diccionaris segons la seva categoria funcional (Generadors, Consumidors
        o Sistemes d'Emmagatzematge) per ser utilitzats posteriorment en el càlcul del balanç energètic.

        :return: True si s'han trobat i carregat configuracions amb èxit; False si no hi ha cap fitxer de configuració disponible.
        :raises ValueError: Si un dispositiu pertany a una categoria no reconeguda.
        """

        configs_saved = [os.path.basename(f) for f in glob.glob(self.base_filepath + "optimizations/configs/*.json")]
        if len(configs_saved) == 0:
            return False

        for config in configs_saved:
            config_path = os.path.join(self.base_filepath, "optimizations/configs", f"{config}")
            with open(config_path, "r",encoding="utf-8") as f:
                current_config = json.load(f)


            dev = create_device_from_config(current_config, self.database)

            device_category = current_config['device_category']
            device_type = current_config['device_type']

            if device_category == "Generator":
                self.generators[device_type] = dev
            elif device_category == "Consumer":
                self.consumers[device_type] = dev
            elif device_category == "EnergyStorage":
                self.energy_storages[device_type] = dev
            else:
                raise ValueError(f"Categoria '{device_category}' desconeguda per al dispositiu {device_type}")

        return True

    def get_sensor_forecast_data(self,sensor_id, today):
        """
        Recupera la predicció de dades d'un sensor específic per a un dia determinat i l'alinea temporalment.

        Aquest mètode obté les dades de forecast des de la base de dades, calcula el rang de temps
        pertinent segons l'horitzó d'optimització (avui o demà) i reconstrueix una sèrie temporal
        completa. En cas que falten dades per a hores específiques dins de la finestra temporal
        definida, s'omplen amb zeros.

        :param sensor_id: Identificador únic del sensor en el sistema.
        :param today: Booleà que indica si es volen les dades del dia actual (True) o de l'endemà (False).
        :return:Una tupla que conté: ([1.2, 0.5, 0.0, . . . ], ['2026-05-13 00:00', '2026-05-13 01:00', . . .])
        """

        if today:
            date_str = datetime.today().strftime('%d-%m-%Y')
            forecast_date = datetime.now()
        else:
            date_str = (datetime.today() + timedelta(days=1)).strftime('%d-%m-%Y')
            forecast_date = datetime.now() + timedelta(days=1)

        sensor_forecast = self.database.get_data_from_forecast_from_date_and_sensorID(sensor_id=sensor_id, date=date_str)

        start_date = datetime(forecast_date.year, forecast_date.month, forecast_date.day, 0,0)
        end_date = start_date + timedelta(hours = self.horizon - 1)
        self.timestamps = pd.date_range(start=start_date, end=end_date, freq='h')
        hours = []
        for i in range(len(self.timestamps)): hours.append(self.timestamps[i].strftime("%Y-%m-%d %H:%M"))

        sensor_data = []

        for hour in hours:
            if hour in sensor_forecast['timestamp'].values:
                row = sensor_forecast[sensor_forecast['timestamp'] == hour]
                sensor_data.append(row['value'].values[0])
            else:
                sensor_data.append(0)

        return sensor_data, self.timestamps

    def configure_varbounds(self):
        """
        Estableix els límits inferiors i superiors (*constraints*) per a les variables del problema d'optimització.

        Aquest mètode defineix l'espai de cerca per a l'algorisme mapejant cada dispositiu (consumidors,
        generadors i bateries) a un rang d'índexs dins d'un vector global. Per a cada dispositiu, es
        calculen els límits de potència mínima i màxima per a cada interval de temps de l'horitzó.
        Aquests índexs (`vbound_start` i `vbound_end`) s'emmagatzemen en els objectes de dispositiu
        per permetre la reconstrucció posterior de la solució.

        :return: **scipy.optimize.Bounds** -> Objecte de restriccions que conté els vectors de límits
                 inferiors i superiors per a totes les variables de decisió.
            (
                lb=[0.0, 0.0, ..., -3000.0, -3000.0],
                ub=[1500.0, 1500.0, ..., 3000.0, 3000.0],
                keep_feasible=True
            )
        """

        lb = []
        ub = []
        index = 0
        num_steps = self.horizon * self.horizon_min


        collections = [
            self.consumers.values(),
            self.generators.values(),
            self.energy_storages.values()
        ]

        # CONSUMERS
        for collection in collections:
            for item in collection:
                item.vbound_start = index

                item_min = getattr(item, 'min_power', item.min) # mirem si te min_power (EnergyStorage) per agafar potència, si no te la variable agafem min
                item_max = getattr(item, 'max_power', item.max)

                lb.extend([item_min] * num_steps)
                ub.extend([item_max] * num_steps)
                index += num_steps

                item.vbound_end = index - 1

        bounds = Bounds(lb, ub, True)
        return bounds

    def __optimize(self):
        """
        Executa l'algorisme d'optimització d'Evolució Diferencial (DE) per trobar la millor configuració energètica.

        Aquest mètode privat configura i llança un procés d'optimització estocàstica global basat en
        poblacions. L'objectiu és minimitzar la funció de cost (`self.cost_DE`) dins dels límits
        establerts (`self.varbound`), forçant la integritat de les variables per a una gestió
        discreta (ON/OFF o potència entera). Utilitza una estratègia 'best1bin' amb inicialització
        'halton' per assegurar una bona cobertura de l'espai de cerca.

        :return: Una tupla que conté: \n
            - np.ndarray: Vector de solució òptima amb els valors per a cada variable de decisió. \n
            - float: El valor de la funció de cost per a la millor solució trobada.

              ([1500, 0, 3000, 1, . . .], -12.45)
        """
        logger.info(f"🦖 - Començant optimització  a les {datetime.now().strftime('%Y-%m-%d %H:00')}")

        result = differential_evolution(func = self.cost_DE,
                                        popsize = 150,
                                        bounds = self.varbound,
                                        integrality = [1] * len(self.varbound.lb),
                                        maxiter = self.maxiter,
                                        mutation = (0.15, 0.25),
                                        recombination = 0.7,
                                        tol = 0.0001,
                                        strategy = 'best1bin',
                                        init = 'halton',
                                        disp = True,
                                        updating = 'deferred',
                                        # callback = self.__update_DE_step,
                                        workers = 1
                                        )


        # if not self.database.running_in_ha:
        logger.warning(" OPTIMIZE FINALITZAT")
        logger.debug(f"     ▫️ Status: {result['message']}")
        logger.debug(f"     ▫️ Total evaluations: {result['nfev']}")
        logger.debug(f"     ▫️ Solution: {result['x']}")
        logger.debug(f"     ▫️ Cost: {result['fun']}")


        return result['x'].copy(), result['fun']

    def cost_DE(self, config):
        """
        Funció objectiu per a l'algorisme d'optimització.
        Aquest mètode actua com a interfície entre l'algorisme de cerca global i el motor de càlcul
        energètic. Rep una configuració candidata generada per l'optimitzador i retorna el cost
        associat invocant el mètode intern de balanç total. És la funció que l'algorisme intentarà
        minimitzar iteració rere iteració.

        :param config: Vector de variables de decisió generat per l'algorisme d'optimització.
        :return: El cost econòmic o penalització energètica de la configuració enviada.
                 Exemple:  **4.25** --> cost positiu ||   **-1.12** -> benefici/estalvi.
        """
        return self.__calc_total_balance(config)

    def __update_DE_step(self,bounds, convergence):
        #TODO + Docu: Mirar si el mètode es pot eliminar
        logger.info(f"◽ New Step")
        logger.debug(f"      ▫️ Convergence {convergence}")
        logger.debug(f"      ▫️ Bounds {bounds}")

        logger.debug(f"      ▫️ Current price {self.current_result}")
        logger.debug(f"      ▫️ Best price {self.best_result}")

        if self.current_result < self.best_result:
            logger.debug(f"      ▫️ Updated Best result: {self.best_result} -> {self.current_result}")
            self.best_result = self.current_result
            self.best_result_balance = self.current_result_balance

    def __calc_total_balance(self,config, total = True):
        """
        Calcula el balanç energètic net i el cost econòmic total d'una configuració específica.

        Aquest mètode és el nucli del simulador energètic. Combina les previsions globals de consum i
        generació amb el comportament dels dispositius individuals (consumidors actius, generadors
        i bateries). Calcula el flux d'energia hora a hora i hi aplica els preus de mercat de
        l'electricitat per determinar el cost operatiu total. Si el paràmetre `total` és cert,
        actualitza l'estat actual de la millor solució trobada.

        :param config: Vector de dades amb la configuració candidata per a tots els dispositius.
        :param total: Booleà; si és True, retorna el cost total (float). Si és False, retorna el
                      vector de balanç detallat (list).
        :return: Depenent del paràmetre 'total':
                 --> Si True: El cost econòmic total en unitats monetàries
                 --> Si False: Llista del balanç net per interval
        """

        total_balance = [0] * (self.horizon * self.horizon_min)

        total_consumers, cost_consumers = self.__calc_total_balance_consumer(config)
        total_generators, cost_generators = self.__calc_total_balance_generator(config)

        for hour in range(self.horizon * self.horizon_min):
            total_consumers[hour] += self.global_consumer_forecast['forecast_data'][hour]
            total_generators[hour] += self.global_generator_forecast['forecast_data'][hour]

            total_balance[hour] = total_consumers[hour] - total_generators[hour]

        balance_result, cost_energy = self.__calc_total_balance_energy(config, total_balance)

        if not total: return balance_result


        # ajuntem el consum horari en una sola variable global.
        total_price = cost_consumers + cost_generators + cost_energy

        for hour in range(self.horizon * self.horizon_min):
            total_price += balance_result[hour] * (self.electricity_prices[hour]/1000)

        self.current_result_balance = balance_result
        self.current_result = total_price

        return total_price

    def __calc_total_balance_consumer(self, config):
        """
        Simula el comportament de tots els dispositius consumidors segons una configuració donada.

        Itera sobre la col·lecció de consumidors (com electrodomèstics intel·ligents o càrregues
        programables), extraient del vector global la part de la configuració que correspon a
        cadascun mitjançant els seus índexs de vinculació (`vbound_start` i `vbound_end`).
        Executa la simulació individual de cada dispositiu per obtenir-ne el perfil de consum
        temporal i els costos operatius interns.

        :param config: Vector global de variables de decisió de l'optimitzador.
        :return:Una tupla que conté:
            - llista de floats: Perfil de consum agregat per a tots els consumidors
            - float: Suma dels costos operatius propis de tots els consumidors

            ([float, float, . . .], float)
        """
        total_consumption = [0] * (self.horizon * self.horizon_min)
        total_cost = 0
        for consumer in self.consumers.values():
            start = consumer.vbound_start
            end = consumer.vbound_end

            res_dict = consumer.simula(config[start:end+1].copy(), self.horizon, self.horizon_min)
            total_cost += res_dict.get('total_cost', 0)
            for hour in range(len(res_dict['consumption_profile'])):
                total_consumption[hour] += res_dict['consumption_profile'][hour]

        return total_consumption, total_cost

    def __calc_total_balance_generator(self, config):
        """
        To Do
        :param config:
        :return:
        """
        #TODO + Docu: Documentar quan el tingui fet
        return [0] * (self.horizon * self.horizon_min), 0

    def __calc_total_balance_energy(self, config, total_balance):
        """
        Simula l'impacte dels sistemes d'emmagatzematge (bateries) sobre el balanç energètic net.

        Aquest mètode integra l'activitat de les bateries en el balanç prèviament calculat entre
        consumidors i generadors. Per a cada sistema d'emmagatzematge, extreu la seva part
        corresponent del vector de configuració i executa la seva simulació (càrrega o descàrrega).
        Els valors resultants s'afegeixen al balanç global, modificant la corba d'energia final
        que s'haurà d'importar o exportar a la xarxa elèctrica.

        :param config: Vector global de variables de decisió de l'optimitzador.
        :param total_balance: Llista amb el balanç net actual (Consum - Generació) abans de bateries.
        :return:Una tupla que conté el balanç energètic final després de l'efecte de les bateries i la suma dels costos operatius o degradació dels sistemes d'emmagatzematge.
            ([float, float, . . .], float)
        """

        total_energy_sources = list(total_balance)
        total_cost = 0
        for energy_storage in self.energy_storages.values():
            start = energy_storage.vbound_start
            end = energy_storage.vbound_end

            res_dict = energy_storage.simula(config[start:end+1], self.horizon, self.horizon_min)
            total_cost += res_dict.get('total_cost', 0)

            for hour in range(0, len(total_balance)):
                total_energy_sources[hour] += res_dict['consumption_profile'][hour]

        return total_energy_sources, total_cost

    def get_hourly_electric_prices(self,):
        """
        Descarrega i processa els preus del mercat elèctric marginal (OMIE) per a l'horitzó d'optimització.

        Es connecta al portal d'OMIE per obtenir el fitxer de preus horaris del dia actual. El mètode
        descarrega un fitxer CSV temporal, n'extreu els preus de la darrera columna i els adapta a la
        resolució temporal definida pel sistema (`horizon_min`). Si l'horitzó d'optimització supera
        les 24 hores, el mètode reinicia el cicle de preus per cobrir tot el període.

        :return: Una llista amb el preu de l'energia per a cada interval de l'optimització.
                 Retorna -1 en cas de fallada en la descàrrega.
            [45.12, 45.12, 42.05, 42.05, 38.90, 38.90, . . .]
        """
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

    def get_hourly_config_for_device(self, config):
        """
        Descodifica el vector de solució de l'optimitzador en un format llegible per dispositiu.

        Aquest mètode rep el vector numèric pla generat per l'algorisme d'Evolució Diferencial
        i el fragmenta segons els índexs de vinculació (`vbound_start` i `vbound_end`) de cada
        actuador. El resultat és un diccionari on cada clau és el nom del dispositiu i el valor
        és la seva seqüència de consignes d'activació o potència per a tot l'horitzó.

        :param config: Array de variables de decisió resultant de l'optimització.
        :return: Diccionari amb la planificació detallada per a cada dispositiu.
            {
                'Rentadora': [0.0, 1.0, 1.0, 0.0, . . .],
                'Bateria_Sonnen': [-1500, -1500, 2000, . . .],
                'Escalfador': [1200, 1200, 0, 0, . . .]
            }
        """

        collections = [
            self.consumers.values(),
            self.generators.values(),
            self.energy_storages.values(),
        ]
        all_devices_config = {}

        for collection in collections:
            for item in collection:
                start = item.vbound_start
                end = item.vbound_end

                device_config = config[start:end+1]

                all_devices_config[item.name] = device_config

        return all_devices_config
