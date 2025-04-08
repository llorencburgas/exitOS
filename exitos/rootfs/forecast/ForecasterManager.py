
import pandas as pd
import requests
import joblib
import os

import forecast.Forecaster as forecast
from datetime import datetime, timedelta



current_dir = os.getcwd()


def obtainmeteoData(latitude, longitude):
    """
    Obté el forecast de meteo data per al dia següent i les dades actuals per les coordenades indicades.
    """
    # today = datetime.today().strftime("%Y-%m-%d")
    # tomorrow = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    today = "2025-04-03"
    tomorrow = "2025-04-04"

    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&start_date={today}&end_date={tomorrow}&hourly=temperature_2m,relativehumidity_2m,dewpoint_2m,apparent_temperature,precipitation,rain,weathercode,pressure_msl,surface_pressure,cloudcover,cloudcover_low,cloudcover_mid,cloudcover_high,et0_fao_evapotranspiration,vapor_pressure_deficit,windspeed_10m,windspeed_100m,winddirection_10m,winddirection_100m,windgusts_10m,shortwave_radiation_instant,direct_radiation_instant,diffuse_radiation_instant,direct_normal_irradiance_instant,terrestrial_radiation_instant"
    response = requests.get(url).json()

    meteo_data = pd.DataFrame(response['hourly'])
    meteo_data = meteo_data.rename(columns={'time': 'timestamp'})
    meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp'])

    return meteo_data

def predict_consumption_production(meteo_data:pd.DataFrame, model_name:str='newModel.pkl'):
    """
    Prediu la consumició tenint en compte les hores actives dels assets
    """
    forecaster = forecast.Forecaster(debug=True)
    forecaster.load_model(model_filename=model_name)
    initial_data = forecaster.db['initial_data']

    meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp']).dt.tz_localize(None).dt.floor('h')
    initial_data['timestamp'] = pd.to_datetime(initial_data['timestamp']).dt.tz_localize(None).dt.floor('h')

    print(meteo_data['timestamp'].head())
    print(initial_data['timestamp'].head())

    data = pd.merge(initial_data, meteo_data, on=['timestamp'], how='inner')
    data = data.set_index('timestamp')
    data.index = pd.to_datetime(data.index)


    prediction = forecaster.forecast(data, 'value', forecaster.db['model'])





