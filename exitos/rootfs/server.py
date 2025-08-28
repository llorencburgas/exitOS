import math
import os
import threading
import traceback
import joblib
import schedule
import time
import json
import glob
import random

import plotly.graph_objs as go
import plotly.offline as pyo
import pandas as pd
from pandas import to_datetime

from bottle import Bottle, template, run, static_file, HTTPError, request, response
from datetime import datetime, timedelta
from logging_config import setup_logger
from collections import OrderedDict

from forecast import Forecaster as Forecast
import forecast.ForecasterManager as ForecasterManager
import forecast.OptimalScheduler as OptimalScheduler
import sqlDB as db
import blockchain as Blockchain


# LOGGER COLORS
logger = setup_logger()

# PARÀMETRES DE L'EXECUCIÓ
HOSTNAME = '0.0.0.0'
PORT = 55023

#INICIACIÓ DE L'APLICACIÓ I LA BASE DE DADES
app = Bottle()
database = db.SqlDB()
forecast = Forecast.Forecaster(debug=True)
optimalScheduler = OptimalScheduler.OptimalScheduler()
blockchain = Blockchain.Blockchain()

logger.info("🌳 eXiT OS INICIAT. OBRE LA UIWEB PER COMENÇAR A USAR-LO.")


# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./images/')

@app.get('/resources/<filepath:path>')
def serve_resources(filepath):
    return static_file(filepath, root='./resources/')

@app.get('models/<filepath:path>')
def serve_models(filepath):
    return static_file(filepath, root='./models/')

# Ruta inicial
@app.get('/')
def get_init():
    ip = request.environ.get('REMOTE_ADDR')
    token = database.supervisor_token


    active_sensors = database.get_all_saved_sensors_id()
    return template('./www/main.html',
                    ip = ip,
                    token = token,
                    active_sensors_list = active_sensors)

#Ruta per a configurar quins sensors volem guardar
@app.get('/sensors')
def get_sensors():
    try:

        calling_from = request.query.get("calling_from", "HTML")

        sensors = database.get_all_sensors()
        sensors_id = sensors['entity_id'].tolist()
        sensors_name = sensors['attributes.friendly_name'].tolist()
        sensors_save = database.get_sensors_save(sensors_id)
        sensors_type = database.get_sensors_type(sensors_id)


        context = {
            "sensors_id": [None if pd.isna(v) else v for v in sensors_id],
            "sensors_name": [None if pd.isna(v) else v for v in sensors_name],
            "sensors_save": sensors_save,
            "sensors_type": sensors_type
        }

        if calling_from == "HTML":
            return template('./www/sensors.html')
        else:
            response.content_type = 'application/json'
            return json.dumps(context)
    except Exception as ex:
        error_message = traceback.format_exc()
        return f"Error! Alguna cosa ha anat malament :c : {str(ex)}\nFull Traceback:\n{error_message}"

@app.get('/databaseView')
def database_graph_page():
    sensors_id = database.get_all_saved_sensors_id()
    graphs_html = {}

    return template('./www/databaseView.html', sensors_id=sensors_id, graphs=graphs_html)

@app.route('/get_graph_info', method='POST')
def graphs_view():
    try:
        selected_sensors = request.forms.get("sensors_id")
        selected_sensors_list = [sensor.strip() for sensor in selected_sensors.split(',')] if selected_sensors else []

        date_to_check_input = request.forms.getall("datetimes")
        if  not date_to_check_input:
            start_date = datetime.today() - timedelta(days=30)
            end_date = datetime.today()
        else:
            date_to_check = date_to_check_input[0].split(' - ')
            start_date = datetime.strptime(date_to_check[0], '%d/%m/%Y %H:%M').strftime("%Y-%m-%dT%H:%M:%S") + '+00:00'
            end_date = datetime.strptime(date_to_check[1], '%d/%m/%Y %H:%M').strftime("%Y-%m-%dT%H:%M:%S") + '+00:00'


        sensors_data = database.get_all_saved_sensors_data(selected_sensors_list, start_date, end_date)
        graphs_html = {}

        if len(sensors_data) == 0:
            for sensor in selected_sensors_list:
                graphs_html[sensor] = f'<div class="no-data">No hi ha dades disponibles del sensor {sensor} per a les dates {date_to_check[0]} - {date_to_check[1]}</div>'

        for sensor_id, data in sensors_data.items():
            timestamps = [record[0] for record in data]
            values = [record[1] for record in data if record[1] is not None]

            if not values:
                graphs_html[sensor_id] = f'<div class="no-data">No hi ha dades disponibles del sensor <strong>{sensor_id}</strong> per a les dates {date_to_check[0]} - {date_to_check[1]}</div>'
                continue


            trace = go.Scatter(x=timestamps, y=values, mode='lines', name=f"Sensor {sensor_id}")
            layout = go.Layout(xaxis=dict(title="Timestamp"),
                               yaxis=dict(title="Value "))

            fig = go.Figure(data=[trace], layout=layout)
            graph_html = pyo.plot(fig, output_type='div', include_plotlyjs=False)


            graphs_html[sensor_id] = graph_html

        return json.dumps({"status": "success", "message": graphs_html})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@app.route('/update_sensors', method='POST')
def update_sensors():

    checked_sensors = request.forms.getall("sensor_id")
    all_sensor_types = request.forms.getall("sensor-type")
    sensors = database.get_all_sensors()
    sensors_id = sensors['entity_id'].tolist()

    i = 0
    for sensor_id in sensors_id:
        is_active = sensor_id in checked_sensors
        was_active = database.get_sensor_active(sensor_id)
        if was_active == 0 and is_active:
            database.update_sensor_active(sensor_id, is_active)
            sensor_type = all_sensor_types[i].strip()
            database.update_sensor_type(sensor_id, sensor_type)
        if was_active == 1 and not is_active:
            database.update_sensor_active(sensor_id, is_active)
            database.remove_sensor_data(sensor_id)

        if is_active:
            i += 1


    sensors_name = sensors['attributes.friendly_name'].tolist()
    sensors_save = database.get_sensors_save(sensors_id)
    sensors_type = database.get_sensors_type(sensors_id)


    context = {
        "sensors_id": sensors_id,
        "sensors_name": sensors_name,
        "sensors_save": sensors_save,
        "sensors_type": sensors_type
    }

    return template('./www/sensors.html', sensors=context)

@app.get('/model')
def create_model_page(active_model = "None"):
    try:
        sensors_id = database.get_all_saved_sensors_id()
        models_saved = [os.path.basename(f)
                        for f in glob.glob(forecast.models_filepath + "*.pkl")]

        forecasts_aux = database.get_forecasts_name()
        forecasts_id = []
        for f in forecasts_aux:
            forecasts_id.append(f[0])

        if active_model == "None": active_model = "newModel"

        return template('./www/model.html',
                        sensors_input = sensors_id,
                        models_input = models_saved,
                        forecasts_id = forecasts_id,
                        active_model = active_model)
    except Exception as ex:
        error_message = traceback.format_exc()
        return f"Error! Alguna cosa ha anat malament :c : {str(ex)}\nFull Traceback:\n{error_message}"

def train_model():
    selected_model = request.forms.get("model")
    extra_sensors_id = request.forms.get("sensors_id") if request.forms.get("sensors_id") else None
    config = {}

    keys = request.forms.keys()
    for key in request.forms.keys():
        if key != "model" or key != "sensors_id" or key != 'action':
            value = request.forms.get(key)
            value = value.strip().lower()

            if value in ["true", "false", "null", "none"]:
                if value == "true": config[key] = True
                elif value == "false": config[key] = False
                else: config[key] = None
            elif value.isdigit():
                config[key] = int(value)
            else:
                try:
                    config[key] = float(value)
                except ValueError:
                    config[key] = value

    sensors_id = config.get("sensorsId")
    scaled = config.get("scaled")
    model_name = config.get("modelName")

    config.pop("sensorsId")
    config.pop("scaled")
    config.pop("modelName")
    config.pop('model')
    config.pop("models")
    config.pop("action")
    if 'sensors_id' in config: config.pop('sensors_id')

    if "meteoData" in config:
        meteo_data = True
        config.pop("meteoData")
    else:
        meteo_data = False

    if model_name == "":
        aux = sensors_id.split('.')
        model_name = aux[1]
    if scaled == 'None': scaled = None

    if extra_sensors_id is None:
        extra_sensors_id = None
    elif len(extra_sensors_id) == 1 and extra_sensors_id[0] == "None":
        extra_sensors_id = None
    else:
        if "None" in extra_sensors_id: extra_sensors_id.remove('None')
        extra_sensors_df = {}
        extra_sensors_list = [s.strip() for s in extra_sensors_id.split(',') if s.strip()]
        for s in extra_sensors_list:
            aux = database.get_data_from_sensor(s)
            extra_sensors_df[s] = aux


    sensors_df = database.get_data_from_sensor(sensors_id)

    logger.info(f"Selected model: {selected_model}, Config: {config}")

    lat = optimalScheduler.latitude
    lon = optimalScheduler.longitude

    if selected_model == "AUTO":
        forecast.create_model(data=sensors_df,
                              sensors_id=sensors_id,
                              y='value',
                              escalat=scaled,
                              max_time=config['max_time'],
                              filename=model_name,
                              meteo_data= meteo_data if meteo_data is True else None,
                              extra_sensors_df=extra_sensors_df if extra_sensors_id is not None else None,
                              lat=lat,
                              lon=lon)
    else:
        forecast.create_model(data=sensors_df,
                              sensors_id=sensors_id,
                              y='value',
                              algorithm=selected_model,
                              params=config,
                              escalat=scaled,
                              filename=model_name,
                              meteo_data=meteo_data if meteo_data is True else None,
                              extra_sensors_df= extra_sensors_df if extra_sensors_id is not None else None,
                              lat=lat,
                              lon=lon)

    return model_name

def forecast_model(selected_forecast):
    forecast_df, real_values = ForecasterManager.predict_consumption_production(model_name=selected_forecast)

    forecasted_done_time = datetime.now().replace(second=0, microsecond=0)
    timestamps = forecast_df.index.tolist()
    predictions = forecast_df['value'].tolist()

    rows = []
    for i in range(len(timestamps)):
        forecasted_time = timestamps[i].strftime("%Y-%m-%d %H:%M")
        predicted = predictions[i]
        actual = real_values[i] if i < len(real_values) else None

        rows.append((selected_forecast, forecasted_done_time, forecasted_time, predicted, actual))
    logger.info(f"📈 Forecast realitzat correctament")
    database.save_forecast(rows)

def delete_model():
    selected_model = request.forms.get("models")
    database.remove_forecast(selected_model)

    model_path = forecast.models_filepath + selected_model
    if os.path.exists(model_path):
        os.remove(model_path)
        logger.info(f"Model deleted: {model_path}")
    else:
        logger.error(f"Model {selected_model} not found")

@app.route('/submit-model', method="POST")
def submit_model():
    try:
        action = request.forms.get('action')

        if action == 'train':
            model_name = train_model()
            return create_model_page(model_name)
        elif action == 'forecast':
            selected_forecast = request.forms.get("models")
            forecast_model(selected_forecast)
            forecast_without_suffix = selected_forecast.replace('.pkl', '')
            return create_model_page(forecast_without_suffix)
        elif action == 'delete':
            delete_model()
            return create_model_page()


    except Exception as e:
        error_message = traceback.format_exc()
        return f"Error! The model could not be processed : {str(e)}\nFull Traceback:\n{error_message}"

@app.route('/get_model_config/<model_name>')
def get_model_config(model_name):
    try:
        model_path = os.path.join(forecast.models_filepath,f"{model_name}.pkl")
        config = dict()
        with open(model_path, 'rb') as f:
            config = joblib.load(f)

        response_config = ""
        response_config += f"algorithm = {config.get('algorithm','')}\n"
        response_config += f"scaler = {config.get('scaler_name','')}\n"
        response_config += f"sensorsId = {config.get('sensors_id','')}\n"
        response_config += f"meteo_data = {str(config.get('meteo_data_is_selected', False)).lower()}\n"

        extra = config.get('extra_sensors', {})
        extra_sensors_id = ",".join(extra.keys()) if isinstance(extra, dict) else ''
        response_config += f"extra_sensors = {extra_sensors_id}\n"

        if "params" in config:
            for k, v in config["params"].items():
                if k == 'bootstrap':
                    aux = 'true' if v else 'false'
                    response_config += f"{k} = {aux}\n"
                elif k == 'algorithm':
                    response_config += f"KNN_algorithm = {v}\n"
                else:
                    response_config += f"{k} = {v}\n"
        if "max_time" in config:
            response_config += f"max_time = {config['max_time']}\n"

        return response_config

    except Exception as e:
        return f"Error! : {str(e)}"

@app.route('/get_forecast_data/<model_name>')
def get_forecast_data(model_name):
    try:
        forecasts = database.get_data_from_latest_forecast(model_name + ".pkl")
        if forecasts.empty:
            return json.dumps({"status":"no_forecasts"})

        timestamps = forecasts["timestamp"].tolist()
        predictions = forecasts["value"].tolist()
        real_values = forecasts["real_value"].tolist()

        #separem dades reals de prediccions futures
        overlapping_timestamps = []
        overlapping_predictions = []
        real_vals = []

        future_timestamps = []
        future_predictions = []

        today = datetime.today()
        first_day = today - timedelta(days=7)

        for i in range(len(timestamps)):
            if not math.isnan(real_values[i]):
                overlapping_timestamps.append(timestamps[i])
                overlapping_predictions.append(predictions[i])
                real_vals.append(real_values[i])
            else:
                future_timestamps.append(timestamps[i])
                future_predictions.append(predictions[i])

        #Calculem timestamps pel Plotly
        last_timestamp = None
        if future_timestamps:
            last_timestamp = datetime.strptime(future_timestamps[-1], "%Y-%m-%d %H:%M")
        elif overlapping_timestamps:
            last_timestamp = datetime.strptime(overlapping_timestamps[-1], "%Y-%m-%d %H:%M")
        if last_timestamp:
            start_timestamp = last_timestamp - timedelta(days=7)
        else:
            start_timestamp = datetime.today() - timedelta(days=7)
            last_timestamp = datetime.today()


        return json.dumps({
            "status": "ok",
            "timestamps_overlap": overlapping_timestamps,
            "predictions_overlap": overlapping_predictions,
            "real_values": real_vals,
            "timestamps_future": future_timestamps,
            "predictions_future": future_predictions,
            "last7daysStart": start_timestamp.strftime("%Y-%m-%d %H:%M"),
            "last7daysEnd": last_timestamp.strftime("%Y-%m-%d %H:%M"),
        })
    except Exception as e:
        logger.error(f"❌ Error getting forecast for model {model_name}: {e}")
        return json.dumps({"status": "error", "message": str(e)})

@app.route('/force_update_database')
def force_update_database():
    database.update_database("all")
    database.clean_database_hourly_average()
    return "ok"

@app.route('/config_page')
def config_page():

    sensors_id = database.get_all_saved_sensors_id(kw=True)
    user_lat = optimalScheduler.latitude
    user_long = optimalScheduler.longitude
    user_location = {'lat': user_lat, 'lon': user_long}

    config_dir = forecast.models_filepath + 'config/user.config'
    user_data = {
        'name': '',
        'consumption': '',
        'generation': '',
        'locked': False,
    }

    if os.path.exists(config_dir):
        aux = joblib.load(config_dir)
        user_data['name'] = aux['name']
        user_data['consumption'] = aux['consumption']
        user_data['generation'] = aux['generation']
        user_data['locked'] = True


    return template('./www/config_page.html',
                    sensors = sensors_id,
                    location = user_location,
                    user_data = user_data)

@app.post('/save_config')
def save_config():
    try:

        data = request.json
        consumption = data.get('consumption')
        generation = data.get('generation')
        name = data.get('name')


        config_dir = forecast.models_filepath + 'config/user.config'
        os.makedirs(forecast.models_filepath + 'config', exist_ok=True)

        database.update_sensor_active(sensor=consumption, active=True)
        database.update_sensor_active(sensor=generation, active=True)

        numero_entero = random.randint(0, 9999999999)
        claves = blockchain.generar_claves_ethereum(f"esta es mi frase secreta para generar claves {numero_entero}")
        logger.info(f"Clau privada: {claves['private_key']}")
        logger.info(f"Dirección Ethereum : {claves['public_key']}")
        res_add_user = blockchain.registrar_usuario(claves['public_key'], claves['private_key'])
        logger.debug(f"res_add_user: {res_add_user}")




        joblib.dump({ 'consumption': consumption,
                            'generation': generation,
                            'name' : name,
                            'public_key': claves['public_key'],
                            'private_key': claves['private_key']}, config_dir)

        logger.info(f"Configuració guardada al fitxer {config_dir}")

        certificate_hourly_task()
        return "OK"

    except Exception as e:
        logger.error(f"Error saving config file :c : {str(e)}")
        logger.error(traceback.format_exc())
        return f"Error! : {str(e)}"

@app.route('/delete_config', method='DELETE')
def delete_config():
    user_config_path = forecast.models_filepath + '/config/user.config'
    if os.path.exists(user_config_path):
        aux = joblib.load(user_config_path)
        consumption = aux['consumption']
        generation = aux['generation']
        database.update_sensor_active(sensor=consumption, active=False)
        database.update_sensor_active(sensor=generation, active=False)

        os.remove(user_config_path)
        return 'Config file deleted successfully'
    else:
        return 'Config file not found'

@app.route('/get_res_certify_data')
def get_res_certify_data():
    try:
        full_path = os.path.join(forecast.models_filepath, "config", "res_certify.pkl")
        status = "ERROR"
        data = {}

        if os.path.exists(full_path):
            data = joblib.load(full_path)
            status = "OK"
            logger.warning(data)

        return json.dumps({
            "status": status,
            "data": data
        })

    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Error! : {str(e)}"

@app.route('/optimize')
def optimize():
    # result = optimalScheduler.optimize()
    template_result = database.get_devices_info()
    if template_result == -1:
        return "ERROR"

    try:
        dades = json.loads(template_result)  # primer decode
        for dispositiu in dades:
            logger.warning(f"\n📟 Dispositiu: {dispositiu['device_name']}")
            logger.debug(f"    🔗 ID: {dispositiu['device_id']}")

            for entitat in dispositiu["entities"]:
                logger.info(f"\n  🔘 Entitat: {entitat['entity_name']} (estat: {entitat['entity_state']})")

                attrs = entitat.get("entity_attrs", {})
                if not attrs:
                    logger.debug("    ⚠️ No hi ha atributs disponibles.")
                    continue

                for clau, valor in attrs.items():
                    if isinstance(valor, (list, dict)):
                        # Mostrem el valor com a JSON "one-line", però compacte
                        valor_str = json.dumps(valor, ensure_ascii=False)
                    else:
                        valor_str = str(valor)
                    logger.debug(f"    🔸 {clau}: {valor_str}")


    except Exception as e:
        logger.exception(f"❌ Error processant la resposta JSON: {e}")

    return "OK"

# Ruta dinàmica per a les pàgines HTML
@app.get('/<page>')
def get_page(page):
    # Ruta del fitxer HTML
    # file_path = f'./www/{page}.html'
    # Comprova si el fitxer existeix.
    if os.path.exists(f'./www/{page}.html'):
        # Control de dades segons la pàgina
        return static_file(f'{page}.html', root='./www/')
    elif os.path.exists(f'./www/{page}.css'):
        return static_file(f'{page}.css', root='./www/')
    else:
        return HTTPError(404, "La pàgina no existeix")


##################################### SCHEDULE

def daily_task():
    logger.debug(f"Running daily task at {datetime.now().strftime('%d-%b-%Y   %X')}")

    logger.debug("STARTING DAILY SENSOR UPDATE")

    database.update_database("all")
    database.clean_database_hourly_average()

    logger.debug("ENDING DAILY SENSOR UPDATE")

def monthly_task():
    today = datetime.today()
    last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1) #últim dia del mes
    if today == last_day:
        sensors_id = database.get_all_sensors()
        sensors_id = sensors_id['entity_id'].tolist()

        for sensor_id in sensors_id:
            is_active = database.get_sensor_active(sensor_id)
            if not is_active:
                database.remove_sensor_data(sensor_id)

        logger.debug(f"Running monthly task at {datetime.now().strftime('%d-%b-%Y   %X')}" )

def daily_train_model(model_config, model_name):
    logger.debug(f"****** Running daily train for {model_name} ******")
    algorithm = model_config.get('algorithm')
    scaler = model_config.get('scaler_name', '')

def daily_forecast_task():
    logger.debug("STARTING DAILY FORECASTING")
    models_saved = [os.path.basename(f) for f in glob.glob(forecast.models_filepath + "*.pkl")]
    for model in models_saved:
        model_path = os.path.join(forecast.models_filepath, f"{model}")
        with open(model_path, 'rb') as f:
            config = joblib.load(f)
        aux = config.get('algorithm','')
        if aux != '':
            # daily_train_model(config, model)
            logger.debug(f"*********** Running daily forecast for {model} **********")
            forecast_model(model)
    logger.debug("ENDING DAILY TASKS")

def certificate_hourly_task():
    logger.info(f"🕒 Running certificate hourly task at {datetime.now().strftime('%H:%M')}")
    config_dir = forecast.models_filepath + 'config/user.config'
    if os.path.exists(config_dir):
        aux = joblib.load(config_dir)
        consumption = aux['consumption']
        generation = aux['generation']
        public_key = aux['public_key']
        private_key = aux['private_key']

        now = datetime.now()


        if  database.get_sensor_active(generation) == 1 and generation != "None":
            database.update_database(generation)
            generation_data = database.get_latest_data_from_sensor(sensor_id=generation)
            generation_timestamp = to_datetime(generation_data[0]).strftime("%Y-%m-%d %H:%M")
            generation_value = generation_data[1]
        else:
            logger.warning(f"⚠️ Recorda seleccionar el sensor de Generació i marcar-lo a l'apartat 'Sensors' per a guardar.")
            generation_timestamp = None
            generation_value = None

        if database.get_sensor_active(consumption) == 1 and consumption != 'None':
            database.update_database(consumption)
            consumption_data = database.get_latest_data_from_sensor(sensor_id=consumption)
            consumption_timestamp = to_datetime(consumption_data[0]).strftime("%Y-%m-%d %H:%M")
            consumption_value = consumption_data[1]
        else:
            logger.warning(f"⚠️ Recorda seleccionar el sensor de Consum i marcar-lo a l'apartat 'Sensors' per a guardar.")
            consumption_timestamp = None
            consumption_value = None


        to_send_string = f"Consumption_{consumption_timestamp}_{consumption_value}_Generation_{generation_timestamp}_{generation_value}_{public_key}_{now}"

        res_certify = blockchain.certify_string(public_key, private_key, to_send_string)

        if res_certify:
            full_path = os.path.join(forecast.models_filepath, "config", "res_certify.pkl")

            if os.path.exists(full_path):
                data_to_save = joblib.load(full_path)
            else:
                data_to_save = {}

            now = now.strftime("%Y-%m-%d %H:%M")

            is_success = res_certify['success']
            if is_success:
                data_to_save[now] = res_certify['response']['transactionHash']
            else:
                data_to_save[now] = "Error"

            data_to_save = dict(OrderedDict(sorted(data_to_save.items())[-10:]))

            joblib.dump(data_to_save, full_path)

        logger.info("🕒 CERTIFICAT HORARI COMPLETAT")
        database.clean_database_hourly_average()

    else:
        logger.warning(f"Encara no t'has unit a cap comunitat! \n"
                       f"Recorda completar la teva configuració d'usuari des de l'apartat 'configuració' de la pàgina")

schedule.every().day.at("00:00").do(daily_task)
schedule.every().day.at("01:00").do(daily_forecast_task)
schedule.every().day.at("02:00").do(monthly_task)
schedule.every().hour.at(":00").do(certificate_hourly_task)

def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(60)

scheduler_thread = threading.Thread(target=run_scheduled_tasks, daemon=True)
scheduler_thread.start()

##################################### MAIN


# Funció main que encén el servidor web.
def main():
    run(app=app, host=HOSTNAME, port=PORT)


# Executem la funció main
if __name__ == "__main__":
    main()