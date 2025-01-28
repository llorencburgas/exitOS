# -*- coding: utf-8 -*-
import sqlite3
import time
import pandas as pd
from requests import get
import traceback
import os
import configparser
import numpy as np
import logging


class sqlDB():
    def __init__(self):
        '''
        Constructor de la classe. Crea la connexió a la base de dades
        '''
        # Nom de la base de dades
        self.filename = "/share/exitos/dades.db"
        self.config_path = '/share/exitos/user_info.conf'
        
        #per conectar a la api de home assistant
        self.supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        self.base_url = "http://supervisor/core/api/"
        self.headers = {
                    "Authorization": "Bearer " + self.supervisor_token,
                    "content-type": "application/json",
                    }

        # Comprova si la base de dades existeix
        if not os.path.isfile(self.filename):
            print("No s'ha trobat la BDD. La creem de nou!")
            "No existeix, creem la base de dades de nou"
            self.__install__()  # Assegura't que aquest mètode està definit i funciona correctament
            
        # Connexió a la base de dades
        self.__con__ = sqlite3.connect(self.filename, timeout=10)
    
    def __del__(self):
        '''
        Destructor de l'objecte. Tanca la connexió de manera segura
        '''
        try:
            self.__con__.close()  # Tanca la connexió, si existeix
        except AttributeError:
            pass  # Si la connexió no existeix, no fem res
    
    def __install__(self):
        '''
        Crea les taules inicials de la BDD
        '''
        print("Creem una BDD nova")
        con = sqlite3.connect(self.filename)        
        cur = con.cursor()
        
        #creem les taules
        cur.execute("CREATE TABLE dades(sensor_id TEXT, timestamp NUMERIC, value)")       
        cur.execute("CREATE TABLE sensors(sensor_id TEXT, units TEXT, description TEXT, update_sensor BINARY)")
        
        con.commit()
        con.close()
        
    def get_sensor_names_W(self):
        '''
        Returns a list of sensors that measure energy in W or kW
        '''
        # Send a GET request to the Home Assistant API to fetch the sensor data
        response = get(self.base_url + 'states', headers=self.headers)
        
        # Flatten the nested JSON response into a DataFrame
        sensors_list = pd.json_normalize(response.json())
        
        # Check if the 'entity_id' column exists in the response data
        if 'entity_id' in sensors_list.columns:
            aux = sensors_list[['entity_id', 'attributes.unit_of_measurement']] # Create a temporary DataFrame 'aux' cotaining 'entity_id' and 'unist_of_measurement'
            llista = aux[aux['attributes.unit_of_measurement'] == 'W'] # Filter the sensors that measure energy in Wh or kWh
            llista = pd.concat([llista, aux[aux['attributes.unit_of_measurement'] == 'kW']]) # Add sensors that measure energy in kWh
            return llista # Return the list of sensors
        else:
            # If 'entity_id' is not found, print and error message and list available columns
            print("'entity_id' column not found in response data")
            print(f"Available columns: {sensors_list.columns.tolist()}")
            # Return a failure message
            return "Doesn't work"

    def get_latitude_longitude(self):
            '''
            Returns the latitude and longitude of the Home Assistant instance
            '''

            # Send a GET request to the Home Assistant API to fetch the sensor data
            response = get(self.base_url + 'config', headers=self.headers)

            # Flatten the nested JSON response into a DataFrame
            config = pd.json_normalize(response.json())

            # Check if the 'latitude' and 'longitude' columns exist in the response data
            if 'latitude' in config.columns and 'longitude' in config.columns:
                # Return the latitude and longitude
                latitude = config['latitude'][0]
                longitude = config['longitude'][0]

                return latitude, longitude
            else:
                # If 'latitude' or 'longitude' is not found, print and error message and list available columns
                print("'latitude' or 'longitude' column not found in response data")
                print(f"Available columns: {config.columns.tolist()}")
                # Return a failure message
                return "Doesn't work"
    
    def get_data_from_db(self, sensors_id):
        """
        Select values from the database for the given sensors.
        """
        merged_data = pd.DataFrame()
        # Connect to the database
        with sqlite3.connect(self.filename) as con:
            for sensor_id in sensors_id:
                try:
                    query = """
                        SELECT timestamp, value
                        FROM dades
                        WHERE sensor_id = ? 
                    """
                    sensor_data = pd.read_sql_query(query, con, params=(sensor_id,))
                    
                    # Assegura't que 'timestamp' és datetime
                    sensor_data['timestamp'] = pd.to_datetime(sensor_data['timestamp'], format='ISO8601')

                    # Renombrar la columna 'value'
                    #sensor_data = sensor_data.rename(columns={'value': f'value_{sensor_id}'})
                    #print(f"Data for sensor_id '{sensor_id}': \n{sensor_data}")

                    # Comprova si merged_data està buit
                    if merged_data.empty:
                        merged_data = sensor_data
                    else:
                        # Fusionar amb merged_data
                        merged_data = pd.merge(merged_data, sensor_data, on='timestamp', how='outer')
                    
                    #print(f"Merged data after adding sensor_id '{sensor_id}': \n{merged_data}")

                except Exception as e:
                    print(f"Error querying sensor_id '{sensor_id}': {e}")
        
        # Comprova si merged_data no està buit abans de fer sort_values
        if not merged_data.empty:
            merged_data = merged_data.sort_values(by='timestamp').reset_index(drop=True)
        else:
            print("merged_data is empty. Skipping sort_values.")

        #print("Final merged data: \n", merged_data)
        return merged_data
    

    def get_config_values(self):
        '''
        Returns the values of the API configuration and the sensor list
        '''
        return self.headers, self.base_url, self.get_sensor_names()
    
    def query(self, sql):
        '''
        Executa una query a la base de dades
        '''
        cur = self.__con__.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        cur.close()

        return result

    def update(self):
        '''
        Actualitza la base de dades amb les dades de la API de Home Assistant
        '''

        try:
            logging.info("Iniciant l'actualització de la base de dades...")
            
            sensors_list = pd.json_normalize(get(self.base_url + 'states', headers=self.headers).json())  # obtenció llista sensors de la API convertits en DataFrame
            
            for j in sensors_list.index:  # per cada sensor de la llista         
                id_sensor = sensors_list.iloc[j]['entity_id']  # es guarda el id del sensor
                
                # comprova si el sensor ja existeix a la base de dades
                with self.__con__.cursor() as cur:
                    var = (id_sensor,)
                    sensor_data = cur.execute('SELECT * FROM sensors WHERE sensor_id = ?', var).fetchall()
                    
                # si el sensor no existeix, el crea
                if not sensor_data:
                    with self.__con__.cursor() as cur:
                        values = (id_sensor, sensors_list.iloc[j]['attributes.unit_of_measurement'], '', True)  # sensor_id, unitats, descripció, update_sensor
                        cur.execute("INSERT INTO sensors(sensor_id, units, description, update_sensor) VALUES(?, ?, ?, ?)", values)
                        self.__con__.commit()
                        logging.info(f'[{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}] Afegint sensor: {id_sensor}')
                else:
                    with self.__con__.cursor() as cur:
                        var = (id_sensor,)
                        last_record = cur.execute('SELECT timestamp, value FROM dades WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1', var).fetchone()
                        if last_record is None:
                            t_ini = "2022-01-01T00:00:00"  # Valor per defecte si no hi ha dades prèvies
                            valor_ant = None
                        else:
                            t_ini, valor_ant = last_record  # Últim timestamp guardat per iniciar des d'allà
                    
                    # Verifica si el sensor ha de ser actualitzat consultant el camp 'update_sensor'
                    with self.__con__.cursor() as cur:
                        var = (id_sensor,)
                        update_sensor_flag = cur.execute('SELECT update_sensor FROM sensors WHERE sensor_id = ?', var).fetchone()[0]
                    
                    if update_sensor_flag:  # Si `update_sensor` és True
                        logging.info(f'[{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}] Actualitzant sensor: {id_sensor}')                   
                        t_fi = "2099-01-01T00:00:00"  # Defineix el final de l'interval de temps per a la crida
                        
                        # Fa una crida a l'API per obtenir l'històric de dades del sensor des de t_ini fins a t_fi
                        url = self.base_url + "history/period/" + t_ini + "?end_time=" + t_fi + "&filter_entity_id=" + id_sensor
                        response = get(url, headers=self.headers)
                        aux = pd.json_normalize(response.json())

                        # Actualitza cada valor obtingut de l'historial del sensor
                        with self.__con__.cursor() as cur:
                            for column in aux.columns:
                                valor = aux[column][0]['state']
                                
                                # Comprova si el valor és vàlid; ignora valors com `unknown`, `unavailable` o buits
                                if valor in ('unknown', 'unavailable', ''):
                                    valor = np.nan
                                
                                # Només desa el valor si és diferent de l'anterior
                                if valor_ant is None or (not np.isnan(valor) and valor_ant != valor):
                                    valor_ant = valor  # Actualitza el valor anterior
                                    TS = aux[column][0]['last_updated']  # Obté el timestamp de l'última actualització
                                    values = (id_sensor, TS, valor)
                                    cur.execute("INSERT INTO dades (sensor_id, timestamp, value) VALUES(?, ?, ?)", values)
                        
                        # Confirma els canvis
                        self.__con__.commit()
                        
        except Exception as e:
            # Gestiona errors, mostrant un missatge d'error i la traça d'errors
            logging.error(f'[{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}] No s\'han pogut inserir o descarregar dades...:(')
            logging.error(traceback.format_exc())

    
    
    
    
    
    