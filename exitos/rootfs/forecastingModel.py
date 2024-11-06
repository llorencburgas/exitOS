from sklearn.linear_model import LinearRegression 
import numpy as np
import sqlDB as db
import configparser
import os

class forecastingModel():
    def __init__(self, config_path='./share/exitos/user_info.conf'):
        '''
        Constructor de la classe
        '''

        self.db = db.sqlDB() # Creem una instància de la base de dades
        self.model = LinearRegression() # Creem una instància del model de regressió lineal
        self.config_path = config_path # Ruta al ficher de configuració

        # Carreguem les dades de configuració
        self.config = self.load_user_info_config()

    def load_user_info_config(self):
        '''
        Carrega les dades de configuració de l'usuari
        '''
        config = configparser.ConfigParser()
        
        # Verifica si el fitxer existeix
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"El fitxer de configuració {self.config_path} no existeix.")

        # Carrega el fitxer de configuració
        config.read(self.config_path)

        # Extreu les dades de la secció 'UserInfo'
        return {
            'asset_id': config.get('UserInfo', 'AssetID', fallback=None),
            'generator_id': config.get('UserInfo', 'GeneratorID', fallback=None),
            'source_id': config.get('UserInfo', 'SourceID', fallback=None),
            'building_consumption_id': config.get('UserInfo', 'BuildingConsumptionID', fallback=None),
            'building_generation_id': config.get('UserInfo', 'BuildingGenerationID', fallback=None)
        }

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