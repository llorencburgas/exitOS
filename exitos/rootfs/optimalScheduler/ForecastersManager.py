import pandas as pd
import requests
import joblib
import os
import optimalScheduler.forecaster as forecast
from datetime import datetime, timedelta
import logging

# Create the prediction and the consumption forecasters from the given models
current_dir = os.getcwd()

prod_forecaster = forecast.Forecaster(debug=True)
cons_forecaster = forecast.Forecaster(debug=True)


# prod_forecaster.load_model("/optimalScheduler/forecasterModels/generationModel.joblib", "/optimalScheduler/forecasterModels/generationScaler.joblib")
# cons_forecaster.load_model("/optimalScheduler/forecasterModels/consumptionModel.joblib", "/optimalScheduler/forecasterModels/consumptionScaler.joblib")

def obtainMeteoData(latitude, longitude):
    """
    Obtains the meteo data forecast for the next day and today's data of the specified latitude and longitude.

    Parameters
    -----------
    latitude : float
    longitude : float
    -----------
    Returns
    -----------
    Returns a DataFrame with the meteo data of size (48, n).
    """
    today = datetime.today().strftime('%Y-%m-%d')
    tomorrow = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&start_date={today}&end_date={tomorrow}&hourly=temperature_2m,relativehumidity_2m,dewpoint_2m,apparent_temperature,precipitation,rain,weathercode,pressure_msl,surface_pressure,cloudcover,cloudcover_low,cloudcover_mid,cloudcover_high,et0_fao_evapotranspiration,vapor_pressure_deficit,windspeed_10m,windspeed_100m,winddirection_10m,winddirection_100m,windgusts_10m,shortwave_radiation_instant,direct_radiation_instant,diffuse_radiation_instant,direct_normal_irradiance_instant,terrestrial_radiation_instant"
    
    response = requests.get(url).json()

    meteo_data = pd.DataFrame(response['hourly'])
    meteo_data = meteo_data.rename(columns={'time': 'timestamp'})
    meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp'])

    return meteo_data


def predictConsumption(model_consumption, meteo_data: pd.DataFrame, scheduling_data: pd.DataFrame):
    """
    Predict the consumption taking into account the active hours scheduled of the assets

    Parameters
    -----------
    meteo_data : DataFrame
        Pandas dataframe with the meteorological data prediction for the next day and the data of today. 
        For example, if predicting the next 24 hours, this parameter must have size (48, n).
    scheduling_data : DataFrame
        Pandas dataframe with the scheduling data relative to the assets that will be optimized for consumption. This dataframe must contain only
        relevant attributes. For now only supported attribute "state". On future work, more attributes could be considered as the model is being updated.
        This parameter must have size (48, m).
    -----------
    Returns
    -----------
    Returns a DataFrame with the consumption prediction with size (24, n + m).
    """ 
    # Normalitza els timestamps per assegurar consistència
    meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp']).dt.tz_localize(None)
    scheduling_data['timestamp'] = pd.to_datetime(scheduling_data['timestamp']).dt.floor('H').dt.tz_localize(None)

    data = pd.merge(scheduling_data, meteo_data, on=['timestamp'], how='inner')
    data = data.set_index('timestamp')
    data.index = pd.to_datetime(data.index)
    
    consumption = prod_forecaster.forecast(data, 'value', model_consumption) #passar la y per parametre
    print("S'ha fet la predicció del consum!")

    return consumption


def predictProduction(model_generation, meteo_data: pd.DataFrame, scheduling_data: pd.DataFrame):
    """
    Predict the production taking into account the active hours scheduled of the assets

    Parameters
    -----------
    meteo_data : DataFrame
        Pandas dataframe with the meteorological data prediction for the next day and the data of today. 
        For example, if predicting the next 24 hours, this parameter must have size (48, n).
    scheduling_data : DataFrame
        Pandas dataframe with the scheduling data relative to the assets that will be optimized for production. This dataframe must contain only
        relevant attributes. For now only supported attribute "state". On future work, more attributes could be considered as the model is being updated.
        This parameter must have size (48, m).
    -----------
    Returns
    -----------
    Returns a DataFrame with the production prediction with size (24, n + m).
    """
    meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp']).dt.tz_localize(None)
    scheduling_data['timestamp'] = pd.to_datetime(scheduling_data['timestamp']).dt.tz_localize(None)

    data = pd.merge(scheduling_data, meteo_data, on=['timestamp'], how='inner')
    data = data.set_index('timestamp')
    data.index = pd.to_datetime(data.index)

    production = cons_forecaster.forecast(data, 'value', model_generation) #passar la y per parametre
    print("S'ha fet la predicció de la producció!")

    return production

