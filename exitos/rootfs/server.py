
import os
import threading

import sqlDB as db
import schedule
import time
import json

import plotly.graph_objs as go
import plotly.offline as pyo
import forecast.Forecaster as forecast
import forecast.ForecasterManager as ForecatManager
import forecast.OptimalScheduler as OptimalScheduler

from bottle import Bottle, template, run, static_file, HTTPError, request, response
from datetime import datetime, timedelta
from logging_config import setup_logger



# LOGGER COLORS
logger = setup_logger()

# PARÀMETRES DE L'EXECUCIÓ
HOSTNAME = '0.0.0.0'
PORT = 55023

#INICIACIÓ DE L'APLICACIÓ I LA BASE DE DADES
app = Bottle()
database = db.sqlDB()
database.update_database("all")
forecast = forecast.Forecaster(debug=True)
optimalScheduler = OptimalScheduler.OptimalScheduler()


#Ruta inicial
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
    return template('./www/main.html',
                    ip = ip,
                    token = token)

#Ruta per a configurar quins sensors volem guardar
@app.get('/sensors')
def get_sensors():
    #TODO: SQLWeb marca 340 sensors, dades.db té 340 sensors, però la llista en rep 329
    sensors = database.get_all_sensors()
    sensors_id = sensors['entity_id'].tolist()
    sensors_name = sensors['attributes.friendly_name'].tolist()
    sensors_save = database.get_sensors_save(sensors_id)


    context = {
        "sensors_id": sensors_id,
        "sensors_name": sensors_name,
        "sensors_save": sensors_save
    }

    return template('./www/sensors.html', sensors = context )

@app.get('/databaseView')
def database_graph_page():
    sensors_id = database.get_all_saved_sensors_id()
    graphs_html = {}

    return template('./www/databaseView.html', sensors_id=sensors_id, graphs=graphs_html)

@app.route('/graphsView', method='POST')
def graphs_view():
    sensors_id = database.get_all_saved_sensors_id()
    selected_sensors = request.forms.get("sensors_id")
    selected_sensors_list = [sensor.strip() for sensor in selected_sensors.split(',')] if selected_sensors else []

    date_to_check = request.forms.getall("datetimes")[0].split(' - ')
    start_date = datetime.strptime(date_to_check[0], '%d/%m/%Y %H:%M').strftime("%Y-%m-%dT%H:%M:%S") + '+00:00'
    end_date = datetime.strptime(date_to_check[1], '%d/%m/%Y %H:%M').strftime("%Y-%m-%dT%H:%M:%S") + '+00:00'

    sensors_data = database.get_all_saved_sensors_data(selected_sensors_list, start_date, end_date)
    graphs_html = {}

    for sensor_id, data in sensors_data.items():
        timestamps = [record[0] for record in data]
        values = [record[1] for record in data]

        if not values:
            graphs_html[sensor_id] = f'<div class="no-data">No data available for Sensor {sensor_id}</div>'
            continue


        trace = go.Scatter(x=timestamps, y=values, mode='lines', name=f"Sensor {sensor_id}")
        layout = go.Layout(title=f"Sensor {sensor_id} Data",
                           xaxis=dict(title="Timestamp"),
                           yaxis=dict(title="Value "))

        fig = go.Figure(data=[trace], layout=layout)
        graph_html = pyo.plot(fig, output_type='div', include_plotlyjs=False)


        graphs_html[sensor_id] = graph_html

    return template('./www/databaseView.html',sensors_id=sensors_id, graphs=graphs_html)


@app.route('/update_sensors', method='POST')
def update_sensors():
    checked_sensors = request.forms.getall("sensor_id")
    sensors = database.get_all_sensors()
    sensors_id = sensors['entity_id'].tolist()

    connection = database.__open_connection__()

    for sensor_id in sensors_id:
        is_active = sensor_id in checked_sensors
        database.update_sensor_active(sensor_id, is_active, connection)

    sensors_name = sensors['attributes.friendly_name'].tolist()
    sensors_save = database.get_sensors_save(sensors_id)

    database.__close_connection__(connection)

    context = {
        "sensors_id": sensors_id,
        "sensors_name": sensors_name,
        "sensors_save": sensors_save
    }

    return template('./www/sensors.html', sensors=context)

@app.get('/forecast')
def forecast_page():
    sensors_id = database.get_all_saved_sensors_id()
    return template('./www/forecast.html', sensors=sensors_id)

@app.route('/submit-forecast', method='POST')
def submit_forecast():
    try:
        selected_model = request.forms.get("model")
        # sensors_id = database.get_all_saved_sensors_id()
        config = {}

        for key in request.forms.keys():
            if key != "model":
                config[key] = request.forms.get(key)


        generation_sensor  = config.get("generationId")
        consumption_sensor = config.get("consumptionId")
        action = config.get("action")
        config.pop("generationId")
        config.pop("consumptionId")
        config.pop("action")

        generation_df = database.get_data_from_sensor(generation_sensor)
        consumption_df = database.get_data_from_sensor(consumption_sensor)

        logger.info(f"Selected model: {selected_model}, Config: {config}")
        logger.info(f"Generation: {generation_sensor}")
        logger.info(f"Consumption: {consumption_sensor}")

        if action == 'train':
            forecast.create_model(data=consumption_df, y='value', escalat="Standard", filename='Consumption')
            forecast.create_model(data=generation_df, y='value', escalat="Standard", filename='Generation')
        elif action == 'forecast':
            consumption = ForecatManager.predict_consumption_production(optimalScheduler.meteo_data, consumption_df)
            logger.debug(consumption)


        return f"Selected Model: {selected_model}, Config: {json.dumps(config)}"
    except Exception as e:
        return f"Error! : {str(e)}"


# Ruta dinàmica per a les pàgines HTML
@app.get('/<page>')
def get_page(page):
    # Ruta del fitxer HTML
    # file_path = f'./www/{page}.html'
    # Comprova si el fitxer existeix
    if os.path.exists(f'./www/{page}.html'):
        # Control de dades segons la pàgina
        return static_file(f'{page}.html', root='./www/')
    elif os.path.exists(f'./www/{page}.css'):
        return static_file(f'{page}.css', root='./www/')
    else:
        return HTTPError(404, "La pàgina no existeix")


##################################### SCHEDULE --> ACTUALITZACIÓ BASE DE DADES DIARIA I NETEJA MENSUAL

def daily_task():
    logger.debug(f"Running daily task at {datetime.now().strftime('%d-%b-%Y   %X')}")

    sensors_id = database.get_all_sensors()
    sensors_id = sensors_id['entity_id'].tolist()

    connection = database.__open_connection__()

    for sensor_id in sensors_id:
        is_active = database.get_sensor_active(sensor_id, connection)
        if is_active:
            database.update_database(sensor_id)

    database.__close_connection__(connection)

def monthly_task():
    today = datetime.today()
    last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1) #últim dia del mes
    if today == last_day:
        sensors_id = database.get_all_sensors()
        sensors_id = sensors_id['entity_id'].tolist()

        connection = database.__open_connection__()

        for sensor_id in sensors_id:
            is_active = database.get_sensor_active(sensor_id, connection)
            if not is_active:
                database.remove_sensor_data(sensor_id, connection)

        database.__close_connection__(connection)
        logger.debug(f"Running monthly task at {datetime.now().strftime('%d-%b-%Y   %X')}" )

schedule.every().day.at("00:00").do(daily_task)
schedule.every().day.at("00:00").do(monthly_task)

def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(60)

scheduler_thread = threading.Thread(target=run_scheduled_tasks, daemon=True)
scheduler_thread.start()

#####################################



#################################################################################
#   Hem acabat de definir totes les url i què cal fer per cada una d'elles.     #
#   Executem el servidor                                                        #
#################################################################################

# Funció main que encén el servidor web.
def main():
    run(app=app, host=HOSTNAME, port=PORT)


# Executem la funció main
if __name__ == "__main__":
    main()