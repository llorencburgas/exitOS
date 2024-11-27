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

    def get_sensor_names(self):
        '''
        Returns a list of sensors that measure energy
        '''
        print("Searching for sensors list")
        sensors = pd.json_normalize(get(self.base_url + 'states', headers=self.headers).json())
        if 'entity_id' in sensors.columns:
            return sensors['entity_id'].tolist()
        else:
            print("'entity_id' column not found in response data")
            print(f"Available columns: {sensors.columns.tolist()}")
            return "Doesn't work"
    
    def get_filtered_data(self, asset_id, generator_id, source_id, building_consumption_id, building_generation_id):
        '''
        Select values from "dades" taken from the user_info.conf file 

        Args:
            asset_id (str): The ID of the asset sensor
            generator_id (str): The ID of the generator sensor
            source_id (str): The ID of the source sensor
            building_consumption_id (str): The ID of the building consumption sensor
            building_generation_id (str): The ID of the building generation sensor
        
        Returns:
            data (dict): A dictionary containing the values of the sensors

        '''
        sensor_ids = [asset_id, generator_id, source_id, building_consumption_id, building_generation_id]

        # Filtra només els sensor_ids vàlids (no buits ni None)
        valid_sensor_ids = [sensor_id for sensor_id in sensor_ids if sensor_id and isinstance(sensor_id, str)]
        print(valid_sensor_ids)

        # Select the values from the dades table
        data = {}

        # Connect to the database
        with sqlite3.connect(self.filename) as con:
            for sensor_id in valid_sensor_ids:
                try:
                    if sensor_id:
                        query = """
                            SELECT timestamp, value
                            FROM dades
                            WHERE sensor_id = ? 
                        """ #Utilitzem placeholders (?) dins de la consulta SQL per evitar problemes d'injecció SQL.
                        data[sensor_id] = pd.read_sql_query(query, con, params=(sensor_id,))
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
            sensors_list = pd.json_normalize(get(self.base_url+'states', headers=self.headers).json()) # obtenció llista sensors de la API convertits en DataFrame
            #print("Llista de sensors de l'API:", sensors_list)  # Depuració per veure la resposta de l'API

            #sensors = self.get_sensor_names_Wh() # obtenció llista de sensors de la BDD
            #sensors = sensors['entity_id'].tolist()
            #print("Llista de sensors de la BDD:", sensors)  # Depuració per veure la resposta de la BDD

            #sensors_list = sensors_list[sensors_list['entity_id'].isin(sensors)] # filtra la llista de sensors de la API amb els de la BDD
            #print("Sensors a actualitzar:", sensors_list)  # Depuració per veure la resposta de la BDD
            
            for j in sensors_list.index: #per cada sensor de la llista         
                id_sensor = sensors_list.iloc[j]['entity_id'] # es guarda el id del sensor
                
                # comprova si el sensor ja existeix a la base de dades
                cur = self.__con__.cursor()
                var = (id_sensor,)
                llista = cur.execute('SELECT * FROM sensors WHERE sensor_id = ?', var).fetchall()
                cur.close()
                
                # si el sensor no existeix, el crea
                if len(llista) == 0:
                    cur = self.__con__.cursor()
                    values = (id_sensor, sensors_list.iloc[j]['attributes.unit_of_measurement'], '', True)  # sensor_id, unitats, descripció, update_sensor
                    cur.execute("INSERT INTO sensors(sensor_id, units, description, update_sensor) VALUES(?, ?, ?, ?)", values)
                    cur.close()
                    self.__con__.commit()
                    print('[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + ' Afegint sensor: ' + id_sensor)
                    llista = None # inicialitza la llista per a la següent iteració
                # si el sensor ja existeix, comprova si cal actualitzar les dades
                else:
                    cur = self.__con__.cursor()
                    var = (id_sensor,)
                    aux = cur.execute('SELECT timestamp, value FROM dades WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1', var).fetchone()
                    if aux is None:
                        # Si no hi ha dades prèvies, inicialitza variables
                        llista = None
                    else:
                        # Assigna el timestamp i el valor anterior per verificar canvis
                        llista, valor_ant = aux
                    cur.close()
                
                # Defineix el temps inicial de l'historial
                if llista is None:
                    t_ini = "2022-01-01T00:00:00"  # Valor per defecte si no hi ha dades prèvies
                    valor_ant = []
                else:
                    t_ini = llista  # Últim timestamp guardat per iniciar des d'allà
                
                # Verifica si el sensor ha de ser actualitzat consultant el camp 'update_sensor'
                cur = self.__con__.cursor()
                var = (id_sensor,)
                llista = cur.execute('SELECT update_sensor FROM sensors WHERE sensor_id = ?', var).fetchall()
                cur.close()
                
                if llista[0][0]:  # Si `update_sensor` és True
                    print('[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + ' Actualitzant sensor: ' + id_sensor)                   
                    t_fi = "2099-01-01T00:00:00" # Defineix el final de l'interval de temps per a la crida
                    
                    # Fa una crida a l'API per obtenir l'històric de dades del sensor des de t_ini fins a t_fi
                    url = self.base_url + "history/period/" + t_ini + "?end_time=" + t_fi + "&filter_entity_id=" + id_sensor
                    aux = pd.json_normalize(get(url, headers=self.headers).json())
                    
                    # Actualitza cada valor obtingut de l'historial del sensor
                    cur = self.__con__.cursor()
                    for column in aux.columns:
                        valor = aux[column][0]['state']
                        
                        # Comprova si el valor és vàlid; ignora valors com `unknown`, `unavailable` o buits
                        if (valor == 'unknown') or (valor == 'unavailable') or (valor == ''):
                            valor = 'nan'
                        
                        # Només desa el valor si és diferent de l'anterior
                        if valor_ant != valor:
                            valor_ant = valor  # Actualitza el valor anterior
                            TS = aux[column][0]['last_updated']  # Obté el timestamp de l'última actualització
                            values = (id_sensor, TS, valor)
                            cur.execute("INSERT INTO dades (sensor_id, timestamp, value) VALUES(?, ?, ?)", values)
                    
                    # Tanca el cursor i confirma els canvis
                    cur.close()
                    self.__con__.commit()
        except:
            # Gestiona errors, mostrant un missatge d'error i la traça d'errors
            print('[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + " No s'han pogut inserir o descarregar dades...:(")
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
    
    
    