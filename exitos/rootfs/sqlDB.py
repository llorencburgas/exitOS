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
        print("Searching for sensors list")
        response = get(self.base_url + 'states', headers=self.headers)
        sensors_list = pd.json_normalize(response.json())
        if 'entity_id' in sensors_list.columns:
            aux = sensors_list[['entity_id', 'attributes.unit_of_measurement']]
            llista = aux[aux['attributes.unit_of_measurement'] == 'Wh']
            llista = pd.concat([llista, aux[aux['attributes.unit_of_measurement'] == 'kWh']])
            return llista
        else:
            print("'entity_id' column not found in response data")
            print(f"Available columns: {sensors_list.columns.tolist()}")
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
            print("Iniciant Update de la BDD")
                
            # Obtenció de la llista de sensors disponibles a Home Assistant en format DataFrame
            sensors_list = pd.json_normalize(get(self.base_url+'states', headers=self.headers).json())
            
            # Itera sobre cada sensor obtingut
            for j in sensors_list.index:                
                # Obté l'ID del sensor actual
                id_sensor = sensors_list.iloc[j]['entity_id']
                
                # Crea un cursor per consultar la base de dades i comprova si el sensor ja existeix
                cur = self.__con__.cursor()
                var = (id_sensor,)
                llista = cur.execute('SELECT * FROM sensors WHERE sensor_id = ?', var).fetchall()
                cur.close()
                
                if len(llista) == 0:
                    # Si el sensor no existeix a la base de dades, el crea
                    cur = self.__con__.cursor()
                    values = (id_sensor, sensors_list.iloc[j]['attributes.unit_of_measurement'], '', True)  # sensor_id, unitats, descripció, update_sensor
                    cur.execute("INSERT INTO sensors(sensor_id, units, description, update_sensor) VALUES(?, ?, ?, ?)", values)
                    cur.close()
                    self.__con__.commit()
                    
                    # Missatge de registre d'afegiment de sensor
                    print('[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + '-- Afegit sensor: ' + id_sensor)
                    
                    # El sensor és nou, no té dades prèvies a la taula de dades
                    llista = None
                else:
                    # Si el sensor ja existeix, comprova si cal actualitzar les dades
                    
                    # Obté el timestamp i l'últim valor desat per aquest sensor
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
                    print('[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + '-- Actualitzant sensor: ' + id_sensor)
                    
                    # Defineix el final de l'interval de temps per a la crida
                    t_fi = "2099-01-01T00:00:00"
                    
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
            print('[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + "-- No s'ha pogut inserir o descarregar dades!")
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
    
    def load_user_info_config(self):
        '''
        Select values from dades taken from the user_info.conf file 
        '''
        config = configparser.ConfigParser()
        config.read(self.config_path)

        # Get the values from the config file
        user_info = {
            'assetid': config.get('UserInfo', 'assetid'),
            'generatorid': config.get('UserInfo', 'generatorid'),
            'sourceid': config.get('UserInfo', 'sourceid'),
            'buildingconsumptionid': config.get('UserInfo', 'buildingconsumptionid'),
            'buildinggenerationid': config.get('UserInfo', 'buildinggenerationid')
        }
        
        # Select the values from the dades table
        data = {}
        for sensor_id in user_info:
            query = """
            SELECT timestamp, value
            FROM dades
            WHERE sensor_id = ?
            """
        data[sensor_id] = pd.read_sql_query(query, self.__con__, params=(user_info[sensor_id],))

        return data