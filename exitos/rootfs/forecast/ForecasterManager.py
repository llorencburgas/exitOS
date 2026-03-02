import pandas as pd
import requests
import joblib
import os

import forecast.Forecaster as Forecast
from datetime import datetime, timedelta
from logging_config import setup_logger
from pandas.core.interchange.dataframe_protocol import DataFrame

logger = setup_logger()
current_dir = os.getcwd()


def get_meteodata(latitude, longitude, archive_meteo:pd.DataFrame, days_foreward):
    """
    Obté les dades meteorològiques de les dates dins el dataframe i afageix 2 dies per predicció
    """

    today = datetime.today().strftime("%Y-%m-%d")
    end_date = (datetime.today() + timedelta(days=days_foreward)).strftime("%Y-%m-%d")

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

    if archive_meteo is not None:
        result = pd.concat([archive_meteo, meteo_data], ignore_index=True)
        return result
    return meteo_data


def predict_consumption_production(model_name, database):
    """
    Prediu la consumició tenint en compte les hores actives dels assets
    """

    forecaster = Forecast.Forecaster(debug=True)

    # Carreguem el model
    forecaster.load_model(model_filename=model_name)
    
    # Obtenim dades actualitzades
    sensors_id = forecaster.db['sensors_id']
    initial_data = database.get_data_from_sensor(sensors_id)

    first_timestamp_metric = initial_data.index[0] if not initial_data.empty else None 

    # Normalitzem timestamps a naive (sense timezone) per ser consistents amb Forecaster.prepare_dataframes
    if not initial_data.empty and 'timestamp' in initial_data.columns:
        initial_data['timestamp'] = pd.to_datetime(initial_data['timestamp']).dt.tz_localize(None)


    meteo_data_boolean = forecaster.db['meteo_data_is_selected']
    if meteo_data_boolean: meteo_data = get_meteodata(forecaster.db['lat'], forecaster.db['lon'], forecaster.db['meteo_data'],2)
    else: meteo_data = None

    original_extra_sensors = forecaster.db['extra_sensors']
    extra_sensors_df = None
    if original_extra_sensors is not None and isinstance(original_extra_sensors, dict):
        extra_sensors_df = {}
        for s in original_extra_sensors.keys():
            aux = database.get_data_from_sensor(s)
            # Normalitzem timestamps a naive per consistència
            if not aux.empty and 'timestamp' in aux.columns:
                aux['timestamp'] = pd.to_datetime(aux['timestamp']).dt.tz_localize(None)
            extra_sensors_df[s] = aux

    data = forecaster.prepare_dataframes(initial_data, meteo_data, extra_sensors_df)

    data = data.set_index('timestamp')
    data.index = pd.to_datetime(data.index)
    data.bfill(inplace=True)


    prediction , real_values , sensor_id = forecaster.forecast(data, 'value', forecaster.db['model'], future_steps=48)

    return prediction, real_values, sensor_id





