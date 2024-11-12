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