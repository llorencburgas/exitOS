from sklearn.linear_model import LinearRegression 
import numpy as np
import sqlDB as db
import configparser
import os
import pandas as pd

class forecastingModel():
    def __init__(self, config_path='./share/exitos/user_info.conf'):
        '''
        Constructor de la classe
        '''

        self.db = db.sqlDB() # Creem una instància de la base de dades
        self.model = LinearRegression() # Creem una instància del model de regressió lineal
        self.config_path = config_path # Ruta al fitxer de configuració

        # Carreguem les dades de configuració
        self.config = self.load_user_info_config()

    def load_user_info_config(self):
        '''
        Carrega les dades de configuració de l'usuari
        '''
        config = configparser.ConfigParser()
        
        # Carrega el fitxer de configuració
        config.read(self.config_path)

        # Extreu els sensor_id de cada secció
        assetid = config.get('UserInfo', 'assetid').strip("[]").replace("'", "").split(',')
        generatorid = config.get('UserInfo', 'generatorid').strip("[]").replace("'", "").split(',')
        sourceid = config.get('UserInfo', 'sourceid').strip("[]").replace("'", "").split(',')
        buildingconsumptionid = config.get('UserInfo', 'buildingconsumptionid').strip("[]").replace("'", "").split(',')
        buildinggenerationid = config.get('UserInfo', 'buildinggenerationid').strip("[]").replace("'", "").split(',')

        # Retorna un diccionari amb els valors carregats
        sensor_ids = assetid + generatorid + sourceid + buildingconsumptionid + buildinggenerationid

        data = {}
        for sensor_id in sensor_ids:
            query = """
                SELECT timestamp, value
                FROM dades
                WHERE sensor_id = ?
                """
            data[sensor_id] = pd.read_sql_query(query, self.db.__con__, params=(sensor_id,))

        return data

    def train_model(self, sensor_id):
        '''
        Entrena el model de regressió lineal amb les dades del sensor
        '''
        # Obtenim les dades del sensor
        data = self.db.get_sensor_data(sensor_id)
        X = np.array(data['timestamp']).reshape(-1, 1)
        y = np.array(data['value']).reshape(-1, 1)

        # Entrenem el model
        self.model.fit(X, y)
        print("Model trained")

    def forecast(self, timestamp):
        '''
        Prediu el valor del sensor en el timestamp donat
        '''
        return self.model.predict(np.array([timestamp]).reshape(-1, 1))
    
    def print_config(self):
        '''
        Mostra els valors carregats des del fitxer de configuració (per verificar)
        '''
        print("Configuració carregada:")
        for key, value in self.config.items():
            print(f"{key}: {value}")