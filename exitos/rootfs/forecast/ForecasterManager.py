import pandas as pd
import requests
import joblib
import os

import forecast.Forecaster as forecast
from datetime import datetime, timedelta
from logging_config import setup_logger


logger = setup_logger()
current_dir = os.getcwd()


def obtainmeteoData(latitude, longitude):
    """
    Obté el forecast de meteo data per al dia següent i les dades actuals per les coordenades indicades.
    """
    today = datetime.today().strftime("%Y-%m-%d")
    end_date = (datetime.today() + timedelta(days=2)).strftime("%Y-%m-%d")

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&start_date={today}&end_date={end_date}"
        f"&hourly=temperature_2m,relativehumidity_2m,dewpoint_2m,apparent_temperature,"
        f"precipitation,rain,weathercode,pressure_msl,surface_pressure,cloudcover,"
        f"cloudcover_low,cloudcover_mid,cloudcover_high,et0_fao_evapotranspiration,"
        f"vapor_pressure_deficit,windspeed_10m,windspeed_100m,winddirection_10m,"
        f"winddirection_100m,windgusts_10m,shortwave_radiation,direct_radiation,"
        f"diffuse_radiation,direct_normal_irradiance,terrestrial_radiation"
    )
    response = requests.get(url).json()

    meteo_data = pd.DataFrame(response['hourly'])
    meteo_data = meteo_data.rename(columns={'time': 'timestamp'})
    meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp'])

    return meteo_data


def predict_consumption_production(meteo_data=None, model_name:str='newModel.pkl'):
    """
    Prediu la consumició tenint en compte les hores actives dels assets
    """
    forecaster = forecast.Forecaster(debug=True)
    forecaster.load_model(model_filename=model_name)
    initial_data = forecaster.db['initial_data']


    meteo_data_boolean = forecaster.db['meteo_data_is_selected']
    if not meteo_data_boolean: meteo_data = None
    extra_sensors_df = forecaster.db['extra_sensors']

    data = forecaster.prepare_dataframes(initial_data, meteo_data, extra_sensors_df)

    data = data.set_index('timestamp')
    data.index = pd.to_datetime(data.index)
    data.bfill(inplace=True)


    prediction , real_values = forecaster.forecast(data, 'value', forecaster.db['model'], future_steps=48)

    return prediction, real_values





