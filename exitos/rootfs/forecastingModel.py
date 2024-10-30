from sklearn.linear_model import LinearRegression 
import numpy as np
import sqlDB as db
import sqlite3

class forecastingModel():
    def __init__(self):
        '''Constructor de la classe'''

        self.db = db.sqlDB()
        self.model = LinearRegression()

        # Connexió a la base de dades
        self.__con__ = sqlite3.connect(self.filename, timeout=10)

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