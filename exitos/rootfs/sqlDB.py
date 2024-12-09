# -*- coding: utf-8 -*-
import sqlite3
import time
import pandas as pd
from requests import get
import traceback
import os
import configparser


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
        
    def get_sensor_names_Wh(self):
        '''
        Returns a list of sensors that measure energy in Wh or kWh
        '''
        # Print a message indicating the start of the sensors search
        print("Searching for sensors list")
        
        # Send a GET request to the Home Assistant API to fetch the sensor data
        response = get(self.base_url + 'states', headers=self.headers)
        
        # Flatten the nested JSON response into a DataFrame
        sensors_list = pd.json_normalize(response.json())
        
        # Check if the 'entity_id' column exists in the response data
        if 'entity_id' in sensors_list.columns:
            # Create a temporary DataFrame 'aux' cotaining 'entity_id' and 'unist_of_measurement'
            aux = sensors_list[['entity_id', 'attributes.unit_of_measurement']]
            # Filter the sensors that measure energy in Wh or kWh
            llista = aux[aux['attributes.unit_of_measurement'] == 'Wh']
            # Add sensors that measure energy in kWh
            llista = pd.concat([llista, aux[aux['attributes.unit_of_measurement'] == 'kWh']])
            # Return the list of sensors
            return llista
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
        '''
        Select values from the database for the given sensors
        Args:
            sensors_id (list): List of sensor IDs to query
        Returns:
            data (dict): A dictionary containing the values of the sensors
        '''

        # Create an empty dictionary to store the data
        data = {}
        # Connect to the database
        with sqlite3.connect(self.filename) as con:
            for sensor_id in sensors_id:
                try:
                    query = """
                        SELECT timestamp, value
                        FROM dades
                        WHERE sensor_id = ? 
                    """ # [?] --> Quan s’executa el codi, el valor de sensor_id s’insereix en el lloc de l’interrogant de forma segura.
                    data[sensor_id] = pd.read_sql_query(query, con, params=(sensor_id,))
                    print(data)
                except Exception as e:
                    print(f"Error querying sensor_id '{sensor_id}': {e}")
                    data[sensor_id] = pd.DataFrame()
        return data
    
    def get_config_values(self):
        '''
        Returns the values of the API configuration and the sensor list
        '''
        return self.headers, self.base_url, self.get_sensor_names()

    def update(self):
        '''
        Actualitza la base de dades amb les dades de la API de Home Assistant
        '''
        try:
            print("Iniciant l'actualització de la base de dades...")
            
            # Obté tots els sensors de la API
            sensors_list = pd.json_normalize(get(self.base_url + 'states', headers=self.headers).json())
            
            # Carrega tots els sensors de la base de dades en un diccionari
            cur = self.__con__.cursor()
            db_sensors = {row[0]: row for row in cur.execute("SELECT sensor_id, update_sensor FROM sensors").fetchall()}
            cur.close()

            # Prepara les operacions de base de dades en bloc
            sensors_to_insert = []
            dades_to_insert = []

            for _, sensor in sensors_list.iterrows():
                id_sensor = sensor['entity_id']
                unit = sensor.get('attributes.unit_of_measurement', None)
                
                if id_sensor not in db_sensors:
                    # Sensor nou
                    sensors_to_insert.append((id_sensor, unit, '', True))
                    print(f"Afegint sensor: {id_sensor}")
                elif db_sensors[id_sensor][1]:  # Si `update_sensor` és True
                    print(f"Actualitzant sensor: {id_sensor}")
                    
                    # Obté l'últim timestamp del sensor
                    cur = self.__con__.cursor()
                    last_data = cur.execute(
                        "SELECT timestamp FROM dades WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1",
                        (id_sensor,)
                    ).fetchone()
                    cur.close()
                    t_ini = last_data[0] if last_data else "2022-01-01T00:00:00"
                    
                    # Obté l'historial del sensor des de l'API
                    t_fi = "2099-01-01T00:00:00"
                    url = f"{self.base_url}history/period/{t_ini}?end_time={t_fi}&filter_entity_id={id_sensor}"
                    history = pd.json_normalize(get(url, headers=self.headers).json())
                    
                    for entry in history.itertuples():
                        valor = entry.state
                        if valor not in ('unknown', 'unavailable', ''):
                            dades_to_insert.append((id_sensor, entry.last_updated, valor))
            
            # Inserta nous sensors
            if sensors_to_insert:
                cur = self.__con__.cursor()
                cur.executemany("INSERT INTO sensors(sensor_id, units, description, update_sensor) VALUES(?, ?, ?, ?)", sensors_to_insert)
                cur.close()
            
            # Inserta dades en bloc
            if dades_to_insert:
                cur = self.__con__.cursor()
                cur.executemany("INSERT INTO dades(sensor_id, timestamp, value) VALUES(?, ?, ?)", dades_to_insert)
                cur.close()
            
            # Confirma canvis
            self.__con__.commit()
        except Exception as e:
            print("Error durant l'actualització:")
            traceback.print_exc()

    def query(self, sql):
        '''
        Executa una query a la base de dades
        '''
        cur = self.__con__.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        cur.close()

        return result
    
    
    