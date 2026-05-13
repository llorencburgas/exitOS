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
    Consulta i combina la previsió meteorològica d'Open-Meteo amb l'històric existent.

    Realitza una petició a l'API per obtenir múltiples variables horàries des d'avui
    fins al nombre de dies especificat, i les concatena amb un DataFrame d'arxiu.

    :param latitude: Latitud per a la consulta meteorològica.
    :param longitude: Longitud per a la consulta meteorològica.
    :param archive_meteo: DataFrame amb dades meteorològiques prèvies o None.
    :param days_foreward: Nombre de dies de previsió a recuperar a partir d'avui.
    :return: DataFrame fusionat amb les dades històriques i la nova previsió.
        pd.DataFrame({
            "timestamp": [datetime, ...],
            "temperature_2m": [float, ...],
            "relativehumidity_2m": [int, ...],
            "cloudcover": [int, ...],
            "windspeed_10m": [float, ...]
        })
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
    Genera una predicció de consum o producció energètica utilitzant un model entrenat.

    Carrega la configuració del model, recupera les dades actualitzades dels sensors
    pertinents i de l'API meteorològica (si s'escau), i executa el pronòstic per a
    les properes 48 hores.

    :param model_name: Nom del fitxer del model a carregar.
    :param database: Instància de la base de dades per recuperar les dades recents.
    :return: Una tupla que conté la predicció, els valors reals ,si n'hi ha, i l'ID del sensor.
    (
        pd.Series([float, ...], index=[datetime, ...]),
        pd.Series([float, ...], index=[datetime, ...]),
        str
    )
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
    else:
        logger.warning(f"   ⚠️ [Forecast] No s'han obtingut dades principals (buides) del sensor {sensors_id}")

    meteo_data_boolean = forecaster.db['meteo_data_is_selected']
    if meteo_data_boolean: 
        meteo_data = get_meteodata(forecaster.db['lat'], forecaster.db['lon'], forecaster.db['meteo_data'],2)
    else: 
        meteo_data = None

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


def train_model(form_data, database, forecaster, lat, lon):
    """
    Configura, processa les dades i entrena un nou model de predicció.

    Extrau els paràmetres del formulari, gestiona la finestra temporal (windowing),
    recupera les dades històriques dels sensors (principal i addicionals) i de
    l'API meteorològica, per finalment delegar la creació del model a l'objecte forecaster.

    :param form_data: Diccionari amb les claus i valors del formulari de la interfície.
    :param database: Instància de la base de dades per obtenir l'històric de sensors.
    :param forecaster: Instància del motor de predicció per entrenar el model.
    :param lat: Latitud per a la integració de dades meteorològiques.
    :param lon: Longitud per a la integració de dades meteorològiques.
    :return: El nom del model creat que s'ha utilitzat per desar el fitxer.
    """
    selected_model = form_data.get("model")
    extra_sensors_id = form_data.get("sensors_id") if form_data.get("sensors_id") else None

    config = {}
    for key, value in form_data.items():
        if key in ("model", "sensors_id", "action"):
            continue
        value = value.strip().lower()
        if value in ["true", "false", "null", "none"]:
            if value == "true":   config[key] = True
            elif value == "false": config[key] = False
            else:                  config[key] = None
        elif value.isdigit():
            config[key] = int(value)
        else:
            try:
                config[key] = float(value)
            except ValueError:
                config[key] = value

    sensors_id   = config.get("sensorsId")
    scaled       = config.get("scaled")
    model_name   = config.get("modelName")
    lang_code    = form_data.get("lang", "ca")

    # Windowing
    windowing_option = config.get("windowingOption", "default")
    look_back = None
    if windowing_option == "24-48":
        look_back = {-1: [24, 48]}
    elif windowing_option == "48-72":
        look_back = {-1: [48, 72]}
    elif windowing_option == "1-24":
        look_back = {-1: [1, 24]}
    elif windowing_option == "custom":
        look_back = {-1: [config.get("windowStart", 25), config.get("windowEnd", 48)]}

    for key in ("sensorsId", "scaled", "modelName", "model", "models", "action",
                "sensors_id", "windowingOption", "windowStart", "windowEnd", "lang"):
        config.pop(key, None)

    if "meteoData" in config:
        meteo_data = True
        config.pop("meteoData")
    else:
        meteo_data = False

    if model_name == "":
        model_name = sensors_id.split('.')[1]
    if scaled == 'None':
        scaled = None

    # Extra sensors
    extra_sensors_df = {}
    if extra_sensors_id is None:
        extra_sensors_id = None
    elif isinstance(extra_sensors_id, list) and len(extra_sensors_id) == 1 and extra_sensors_id[0] == "None":
        extra_sensors_id = None
    elif isinstance(extra_sensors_id, str):
        extra_sensors_list = [s.strip() for s in extra_sensors_id.split(',') if s.strip() and s.strip() != "None"]
        if not extra_sensors_list:
            extra_sensors_id = None
        else:
            for s in extra_sensors_list:
                aux = database.get_data_from_sensor(s)
                if not aux.empty and 'timestamp' in aux.columns:
                    aux['timestamp'] = pd.to_datetime(aux['timestamp'])
                    if aux['timestamp'].dt.tz is None:
                        aux['timestamp'] = aux['timestamp'].dt.tz_localize('UTC')
                extra_sensors_df[s] = aux

    sensors_df = database.get_data_from_sensor(sensors_id)
    if not sensors_df.empty and 'timestamp' in sensors_df.columns:
        sensors_df['timestamp'] = pd.to_datetime(sensors_df['timestamp'])
        if sensors_df['timestamp'].dt.tz is None:
            sensors_df['timestamp'] = sensors_df['timestamp'].dt.tz_localize('UTC')

    logger.info(f"Selected model: {selected_model}, Config: {config}, Windowing: {look_back}")

    common_kwargs = dict(
        data=sensors_df,
        sensors_id=sensors_id,
        y='value',
        escalat=scaled,
        filename=model_name,
        meteo_data=meteo_data if meteo_data else None,
        extra_sensors_df=extra_sensors_df if extra_sensors_id is not None else None,
        lat=lat,
        lon=lon,
        look_back=look_back,
        lang=lang_code,
    )

    if selected_model == "AUTO":
        forecaster.create_model(**common_kwargs, max_time=config['max_time'])
    else:
        forecaster.create_model(**common_kwargs, algorithm=selected_model, params=config)

    return model_name


def forecast_model(selected_forecast, database, models_filepath, today=True):
    """
    Executa la predicció d'un model específic i emmagatzema els resultats a la base de dades.

    Crida la funció de predicció per obtenir els valors estimats i reals, filtra les
    dades per mantenir només els últims 14 dies (més la previsió futura) i desa el
    conjunt resultant amb la marca de temps de l'execució.

    :param selected_forecast: Nom del fitxer del model (.pkl) a utilitzar.
    :param database: Instància de la base de dades on es guardaran els resultats.
    :param models_filepath: Ruta on s'allotgen els fitxers dels models.
    :param today: Booleà que defineix si la data objectiu és avui o demà.
    """
    forecast_df, real_values, sensor_id = predict_consumption_production(
        model_name=selected_forecast, database=database
    )

    if today:
        forecasted_done_time = datetime.today().strftime('%d-%m-%Y')
    else:
        forecasted_done_time = (datetime.today() + timedelta(days=1)).strftime("%d-%m-%Y")

    logger.info(f"   📅 [Forecast] {selected_forecast} → data objectiu: {forecasted_done_time}")

    timestamps  = forecast_df.index.tolist()
    predictions = forecast_df['value'].tolist()
    real_vals = real_values.tolist() if hasattr(real_values, 'tolist') else real_values

    rows = []
    # LIMITAR EL GRÀFIC: Només guardem les dades dels últims 14 dies (i futur)
    cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=14)
    cutoff_date = cutoff_date.replace(tzinfo=None)

    for i, ts in enumerate(timestamps):
        ts_naive = ts.replace(tzinfo=None) if hasattr(ts, 'tzinfo') and ts.tzinfo else ts
        if ts_naive >= cutoff_date:
            rows.append((
                selected_forecast,
                sensor_id,
                forecasted_done_time,
                ts.strftime("%Y-%m-%d %H:%M"),
                predictions[i],
                real_vals[i] if i < len(real_vals) else None,
            ))

    database.save_forecast(rows)
    logger.info("   ✅ [Forecast] Forecast realitzat correctament")


def delete_model(model_name, database, models_filepath):
    """
    Elimina un model del sistema, tant de la base de dades com del disc físic.

    Esborra totes les dades de predicció associades al model a la base de dades i,
    posteriorment, elimina el fitxer binari (.pkl) de la carpeta de magatzem.

    :param model_name: Nom del fitxer del model a eliminar (incloent l'extensió).
    :param database: Instància de la base de dades per executar la neteja de registres.
    :param models_filepath: Ruta arrel on s'ubiquen els fitxers de predicció.
    """
    database.remove_forecast(model_name)

    model_path = os.path.join(models_filepath, 'forecastings', model_name)
    if os.path.exists(model_path):
        os.remove(model_path)
        logger.info(f"Model deleted: {model_path}")
    else:
        logger.error(f"Model {model_name} not found")
