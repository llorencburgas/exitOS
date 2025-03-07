# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
from requests import get
import traceback
import os
import configparser
import numpy as np
import logging

from datetime import datetime, timedelta, timezone



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
        self.headers = {"Authorization": "Bearer " + self.supervisor_token,
                        "content-type": "application/json",}

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
        #with sqlite3.connect(self.filename) as con:
        for sensor_id in sensors_id:
            #try:
                query = """
                    SELECT timestamp, value
                    FROM dades
                    WHERE sensor_id = ? 
                """
                sensor_data = pd.read_sql_query(query, self.__con__, params=(sensor_id,))
                
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

            #except Exception as e:
            #    print(f"Error querying sensor_id '{sensor_id}': {e}")
        
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
        Actualitza la base de dades amb les dades de la API de Home Assistant.
        Aquesta funció sincronitza els sensors existents amb la base de dades i actualitza els valors històrics si cal.
        '''

        logging.info("Iniciant l'actualització de la base de dades...")

        # obtenció llista sensors de la API convertits en DataFrame
        sensors_list = pd.json_normalize(get(self.base_url+'states', headers=self.headers).json()) 

        #per cada sensor de la llista
        for j in sensors_list.index:

            #guardem id del sensor
            sensor_id = sensors_list.iloc[j]['entity_id']

            #Obtenim els sensors de la nostra DB que tinguin un id igual al obtingut anteriorment
            cursor = self.__con__.cursor()
            cursor.execute('SELECT * FROM sensors WHERE sensor_id = ?', (sensor_id,))
            aux_list = cursor.fetchall()
            cursor.close()

            #si no hem obtingut cap sensor (és a dir no existeix) el creem com a nou
            if len(aux_list) == 0:
                cursor = self.__con__.cursor()
                values_to_insert = (sensor_id, #ID del sensor
                                    sensors_list.iloc[j]['attributes.unit_of_measurement'], # unitats de mesura
                                    '', #descripció
                                    True) #update_sensor
                cursor.execute("INSERT INTO sensors(sensor_id, units, description, update_sensor) VALUES(?, ?, ?, ?)", values_to_insert)
                cursor.close()
                self.__con__.commit()

                print('[' + datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') +']' 
                      + "Afegint sensor: " + sensor_id)
                aux_list = None #reiniciem la llista per a la següent iteració
            
            #si el sensor Sí que existeix, comprovem si cal actualitzar les dades que tenim
            else:
                cursor = self.__con__.cursor()
                cursor.execute('SELECT timestamp, value FROM dades WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1',(sensor_id,))
                last_data_saved = cursor.fetchone()

                if(last_date_saved == None): last_date_saved = None
                else: last_date_saved, last_value = last_date_saved

                cursor.close()

            
            #si no tenim cap data guardada al sensor
            if(last_date_saved is None):
                start_time = datetime.now(timezone.utc) - timedelta(days=21) #valor per defecte, fa 21 dies
                last_value = []
            else:
                start_time = datetime.fromisoformat(last_data_saved)
            
            # comrpovem si el sensor actual necessita ser actualitzat mirant 'update_sensor'
            cursor = self.__con__.cursor()
            cursor.execute('SELECT update_sensor FROM sensors WHERE sensor_id = ?', (sensor_id,))
            update_sensor = cursor.fetchall()
            cursor.close()

            if(update_sensor[0][0]): #mirem si "update_sensor" és True
                current_time = datetime.now(timezone.utc)
                print('[' + current_time.strftime('%Y-%m-%dT%H:%M:%S') + ']' +
                       ' Actualitzant sensor: ' + sensor_id)  
                
                while(start_time < current_time):
                    print('[' + current_time.strftime('%Y-%m-%dT%H:%M:%S') + ']' +
                           ' Obtenint dades del sensor: ' + sensor_id)  
                    
                    #definim un rang de 7 dies
                    end_time = start_time + timedelta(days = 7)

                    #fem una crida a l'API per obtneir l'històric de dades del sensor dins el rang 
                    string_start_date = start_time.strftime('%Y-%m-%dT%H:%M:%S') 
                    string_end_date = end_time.strftime('%Y-%m-%dT%H:%M:%S')

                    url = (
                        self.base_url + "history/period/" + string_start_date +
                         "?end_time=" + string_end_date +
                         "&filter_entity_id=" + sensor_id 
                        #  + "&minimal_response&no_attributes"
                    )

                    sensor_data_historic = pd.json_normalize(get(url, headers=self.headers).json())
                    print("HISTORIC DE DADES: ", sensor_data_historic)

                    #actualitzem cada valor obtingut de l'historial del sensor
                    cursor = self.__con__.cursor()
                    for column in sensor_data_historic.columns:
                        value = sensor_data_historic[column][0]['state']

                        #mirem si el valor és vàlid
                        if(value == 'unknown') or (value == 'unavailable') or (value == ''):
                            value = np.nan
                        
                        #desem el valor únicament si és diferent a l'anterior
                        if(last_value != value):
                            last_value = value
                            time_stamp = sensor_data_historic[column][0]['last_changed']
                            cursor.execute("INSERT INTO dades (sensor_id, timestamp, value) VALUES(?, ?, ?)",
                                           (sensor_id, time_stamp, value))
                            
                    cursor.close()
                    self.__con__.commit()

                    start_time += timedelta(days=7)




                







        

    
    
    
    
    
    