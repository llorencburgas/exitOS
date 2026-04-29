#region IMPORTS
import os
import threading
import traceback

import joblib
import plotly
import schedule
import time
import json
import glob
import random
import tzlocal

import plotly.graph_objs as go
import pandas as pd
from pandas import to_datetime

from bottle import Bottle, template, run, static_file, HTTPError, request, response
from datetime import datetime, timedelta

from logging_config import setup_logger
from collections import OrderedDict

from forecast import Forecaster as Forecast
import forecast.ForecasterManager as ForecasterManager
import optimization.OptimalScheduler as OptimalScheduler
import optimization.FlexibilityManager as FlexibilityManager
import sqlDB as db
import blockchain as Blockchain
import numpy as np
import llm.LLMEngine as llm_engine

#endregion

# LOGGER COLORS
logger = setup_logger()

# Helper function per convertir tipus NumPy/Pandas a tipus natius de Python
def convert_to_json_serializable(obj):
    """
    Converteix recursivament objectes amb tipus NumPy/Pandas a tipus natius de Python
    per permetre la serialització JSON.
    :param obj: obj que volem convertir de NumPy/Pandas a tipus natiu de Python.
    :return: Retorna l'objecte convertit a tipus Python.
    """
    if isinstance(obj, dict):
        return {key: convert_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return convert_to_json_serializable(obj.tolist())
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif pd.isna(obj):
        return None
    else:
        return obj

# PARÀMETRES DE L'EXECUCIÓ
HOSTNAME = '0.0.0.0'
PORT = 55023


#INICIACIÓ DE L'APLICACIÓ I LA BASE DE DADES
app = Bottle()
database = db.SqlDB()
forecast = Forecast.Forecaster(debug=True)
optimalScheduler = OptimalScheduler.OptimalScheduler(database)
blockchain = Blockchain.Blockchain()

#region DEFINICIÓ EINES LLM
def tool_get_current_time(**kwargs):
    """Retorna l'hora actual del servidor"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def tool_get_current_day(**kwargs):
    """Retorna la data actual (dia, mes i any)"""
    return datetime.now().strftime("%d-%m-%Y")

def tool_get_current_year(**kwargs):
    """Retorna l'any actual"""
    return datetime.now().strftime("%Y")

def tool_get_sensor_value(sensor_id, **kwargs):
    """Retorna l'últim valor conegut d'un sensor específic"""
    try:
        val = database.get_current_sensor_state(sensor_id)
        if val is None:
            data = database.get_latest_data_from_sensor(sensor_id)
            if data:
                return f"El valor de {sensor_id} és {data[1]} (a les {data[0]})"
            else:
                return f"No he trobat dades per al sensor {sensor_id}."
        return f"El valor actual de {sensor_id} és {val}"
    except Exception as e:
        return f"Error llegint sensor: {e}"

def tool_get_optimization_configs(config_name=None, **kwargs):
    """Retorna totes les configuracions d'optimització guardades per l'usuari"""
    try:
        configs_path = os.path.join(forecast.models_filepath, "optimizations/configs")
        if not os.path.exists(configs_path):
            return "No hi ha cap configuració d'optimització guardada."

        json_files = [f for f in os.listdir(configs_path) if f.endswith(".json")]
        
        # Filtre opcional si l'LLM demana un per nom
        if config_name:
            config_name_clean = config_name.replace(".json", "").lower()
            json_files = [f for f in json_files if config_name_clean in f.lower()]
            
        if not json_files:
            if config_name:
                return f"No he trobat cap configuració que coincideixi amb '{config_name}'."
            return "No hi ha cap configuració d'optimització guardada."

        result_lines = []
        for filename in json_files:
            filepath = os.path.join(configs_path, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                cfg = json.load(f)

            device_name = cfg.get("device_name", filename.replace(".json", ""))
            friendly_type = cfg.get("friendly_name", cfg.get("device_type", "Desconegut"))
            category = cfg.get("device_category", "")

            result_lines.append(f"--- Dispositiu: {device_name} ---")
            result_lines.append(f"  Tipus: {friendly_type} (Categoria: {category})")

            restrictions = cfg.get("restrictions", {})
            if restrictions:
                result_lines.append("  Restriccions:")
                for r_id, r_data in restrictions.items():
                    result_lines.append(f"    - {r_data.get('name', r_id)}: {r_data.get('value', '')}")

            extra_vars = cfg.get("extra_vars", {})
            if extra_vars:
                result_lines.append("  Variables de mesura:")
                for v_id, v_data in extra_vars.items():
                    result_lines.append(f"    - {v_data.get('label_name', v_id)}: {v_data.get('friendly_name', v_data.get('sensor_id', ''))}")

            control_vars = cfg.get("control_vars", {})
            if control_vars:
                result_lines.append("  Variables de control:")
                for v_id, v_data in control_vars.items():
                    result_lines.append(f"    - {v_data.get('label_name', v_id)}: {v_data.get('friendly_name', v_data.get('sensor_id', ''))}")

        return "\n".join(result_lines)

    except Exception as e:
        return f"Error llegint les configuracions d'optimització: {e}"

def tool_get_available_device_types(device_type_id=None, **kwargs):
    """Retorna tots els tipus de dispositius disponibles per configurar a l'optimitzador, amb les seves restriccions i variables"""
    try:
        config_path = "resources/optimization_configs/optimization_devices_ca.conf"
        if not os.path.exists(config_path):
            config_path = "resources/optimization_devices_ca.conf"
        if not os.path.exists(config_path):
            return "No s'ha trobat el fitxer de tipus de dispositius."

        with open(config_path, 'r', encoding='utf-8') as f:
            device_types = json.load(f)

        # Filtre opcional
        if device_type_id:
            if device_type_id in device_types:
                device_types = {device_type_id: device_types[device_type_id]}
            else:
                return f"El tipus de dispositiu '{device_type_id}' no existeix. Tipus vàlids: {', '.join(device_types.keys())}"

        result_lines = [
            "=== TIPUS DE DISPOSITIUS DISPONIBLES PER A L'OPTIMITZACIÓ ===",
            "Aquests són els tipus de dispositius que l'usuari pot escollir quan crea una nova configuració d'optimització.",
            ""
        ]

        for type_id, type_data in device_types.items():
            nom = type_data.get("nom", type_id)
            categoria = type_data.get("tipus", "Desconegut")
            result_lines.append(f"--- {nom} (id: {type_id}, categoria: {categoria}) ---")

            restriccions = type_data.get("restriccions", [])
            if restriccions:
                result_lines.append("  Restriccions a configurar:")
                for r in restriccions:
                    if isinstance(r, dict):
                        desc = f"    - {r.get('nom', r.get('id', ''))}"
                        if "min" in r:
                            desc += f" (mínim: {r['min']})"
                        if "max" in r:
                            desc += f" (màxim: {r['max']})"
                        if "step" in r:
                            desc += f" (increment: {r['step']})"
                        result_lines.append(desc)
                    else:
                        result_lines.append(f"    - {r}")

            variables = type_data.get("variables", [])
            if variables:
                result_lines.append("  Variables de mesura (sensors de lectura):")
                for v in variables:
                    result_lines.append(f"    - {v.get('nom', v.get('id', ''))}")

            variables_control = type_data.get("variables_control", [])
            if variables_control:
                result_lines.append("  Variables de control (actuadors):")
                for v in variables_control:
                    result_lines.append(f"    - {v.get('nom', v.get('id', ''))}")

            result_lines.append("")

        result_lines.append(
            "NOTA: Les categories possibles són: 'Consumer' (consumidor d'energia), "
            "'EnergyStorage' (emmagatzematge d'energia, com bateries) i 'Generator' (generador, com plaques solars)."
        )

        return "\n".join(result_lines)

    except Exception as e:
        return f"Error llegint els tipus de dispositius disponibles: {e}"

def tool_get_system_entities(query=None, **kwargs):


    """Retorna la llista de dispositius i entitats (sensors/actuadors) reals del sistema."""
    try:
        devices = database.get_devices_info()
        if not devices:
            return "No he pogut carregar la informació de dispositius del sistema."

        # Si hi ha una query, filtrem
        if query:
            query_clean = query.lower()
            filtered_devices = []
            for d in devices:
                # Comprovem si el nom del dispositiu coincideix
                if query_clean in d.get('device_name', '').lower():
                    filtered_devices.append(d)
                else:
                    # Comprovem si alguna entitat del dispositiu coincideix
                    entities_match = [e for e in d.get('entities', []) 
                                    if query_clean in e.get('entity_id', '').lower() 
                                    or query_clean in e.get('entity_name', '').lower()]
                    if entities_match:
                        # Creem una còpia amb només les entitats que coincideixen
                        d_copy = d.copy()
                        d_copy['entities'] = entities_match
                        filtered_devices.append(d_copy)
            
            devices = filtered_devices

        if not devices:
            return f"No he trobat cap dispositiu o entitat que coincideixi amb '{query}'."

        result_lines = ["=== DISPOSITIUS I ENTITATS DEL SISTEMA (Real-time) ==="]
        for d in devices[:15]: # Limitem per no saturar el context
            name = d.get('device_name', 'Desconegut')
            result_lines.append(f"\n📍 Dispositiu: {name}")
            entities = d.get('entities', [])
            for e in entities[:10]: # Limitem entitats per dispositiu
                e_id = e.get('entity_id', '')
                e_name = e.get('entity_name', '')
                result_lines.append(f"  - {e_name} ({e_id})")
        
        if len(devices) > 15:
            result_lines.append("\n... hi ha més dispositius, sigues més específic si no has trobat el que buscaves.")

        return "\n".join(result_lines)

    except Exception as e:
        logger.error(f"Error a tool_get_system_entities: {e}")
        return f"Error consultant els dispositius: {e}"

#endregion DEFINICIÓ EINES LLM

# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')

#region HTML PAGES

#region core_paths
def serve_static(filepath):
    """
    retorna la imatge sol·licitada del path /images/
    :param filepath: path de la imatge desitjada
    :return: static_file(filepath, root='./images/')
    """
    return static_file(filepath, root='./images/')

@app.get('/resources/<filepath:path>')
def serve_resources(filepath):
    """
    retorna el resource sol·licitada del path /resources/
    :param filepath: path del resource desitjat
    :return: static_file(filepath, root='./resources/')
    """
    return static_file(filepath, root='./resources/')

@app.get('models/<filepath:path>')
def serve_models(filepath):
    """
    retorna el model sol·licitat del path /models/
    :param filepath: path del model
    :return: static_file(filepath, root='./models/')
    """
    return static_file(filepath, root='./models/')

# Ruta dinàmica per a les pàgines HTML
@app.get('/<page>')
def get_page(page):
    """
    Retorna la pàgina HTML sol·licitada
    :param page: pàgina HTML a servir
    :return: pàgina (static file) si existeix, HTTPError 404 en cas contrari
    """
    # Comprova si el fitxer existeix.
    if os.path.exists(f'./www/{page}.html'):
        # Control de dades segons la pàgina
        return static_file(f'{page}.html', root='./www/')
    elif os.path.exists(f'./www/{page}.css'):
        return static_file(f'{page}.css', root='./www/')
    else:
        return HTTPError(404, "La pàgina no existeix")

#endregion core_paths

# Ruta inicial
@app.get('/')
def get_init():
    """
    Obté la pàgina inicial del programa (main.html) i la retorna en format *template* juntament amb la llista de sensors actius.
    :return: Retorna la pàgina inicial del programa en format *template*
    """
    ip = request.environ.get('REMOTE_ADDR')
    token = database.supervisor_token


    aux = database.get_forecasts_name()
    active_sensors = [x[0] for x in aux]

    return template('./www/main.html',
                    ip = ip,
                    token = token,
                    active_sensors_list = active_sensors)

@app.get('/sensors')
def sensors_page():
    """
    Obté la pàgina HTML sensors.html
    :return: pàgina sensors.html en format template
    """
    return template('./www/sensors.html',)

@app.get('/databaseView')
def database_graph_page():
    """
    Obté tots els sensors guardats (ID) i prepara la *template* de graphs.html amb aquesta informació
    :return: Retorna la pàgina graphs.html en format *template*.
    """
    sensors_id = database.get_all_saved_sensors_id()
    graphs_html = {}

    return template('./www/databaseView.html',
                    sensors_id=sensors_id,
                    graphs=graphs_html)

@app.get('/model')
def create_model_page(active_model = "None"):
    """
    Prepara el *template* per a la pàgina model.html obtenint diferents dades que necessita la pàgina per a funcionar:\n
    - **sensors_input**: llista de ID de tots els sensors guardats.\n
    - **models_input**: llista de tots els models guardats en format .pkl a la carpeta forecastings del programa.\n
    - **forecasts_id**: llista de ID dels forecasts guardats a la base de dades.\n
    - **active_model**: nom del model actiu a la pàgina de model.\n

    :param active_model: model de forecasting actiu a la pàgina model.html
    :return: pàgina model.html en format *template* juntament amb sensors_id, els models guardats,
     els id dels forecastings guardats i el model actiu.
    """
    try:
        sensors_id = database.get_all_saved_sensors_id()
        models_saved = [os.path.basename(f)
                        for f in glob.glob(forecast.models_filepath + "forecastings/*.pkl")]

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

@app.route('/config_page')
def config_page():
    """
    Prepara el template per a la pàgina config.html obtenint diferents dades que necessita la pàgina per a funcionar:\n
    - **Sensors**: Llista de ID dels sensors guardats a la base de dades.\n
    - **Location**: Diccionari amb Latitut i Longitud de l'ubicació del Home Asistant.\n
    - **User_data**: Configuració guardada de l'usuari.

    :return: Pàgina config_page.html en format *template*.
    """

    sensors_id = database.get_all_saved_sensors_id(kw=True)
    user_lat = optimalScheduler.latitude
    user_long = optimalScheduler.longitude
    user_location = {'lat': user_lat, 'lon': user_long}

    user_data = get_user_configuration_data()

    return template('./www/config_page.html',
                    sensors = sensors_id,
                    location = user_location,
                    user_data = user_data)

@app.route('/optimization')
def optimization_page():
    """
    Prepara el *template* per a la pàgina optimization.html obtenint diferents dades que necessita la pàgina per a funcionar:\n
    - **Current_date**: data actual en format 'd-m-Y'\n
    - **Device_entities**: Informació sobre els dispositius i entitats filles que conté Home Asistant vinculats.
    :return: Pàgina optimization_page.html en format *template*.
    """

    # DISPOSITIUS I ENTITATS ASSOCIADES
    devices_entities = database.get_devices_info()

    current_date = datetime.now().strftime('%d-%m-%Y')
    return template("./www/optimization.html",
                    current_date = current_date,
                    device_entities = devices_entities)


#endregion PAGE CREATIONS

#region PÀGINA MAIN
@app.route('/get_scheduler_data')
def get_scheduler_data():
    """
    Obté les dades de l'optimització del dia actual per tal de generar una gràfica amb Plotly
    on mostri el consum general previst per a cada hora segons l'optimització.

    :return: figura Plotly codificada en json.dumps()
    """
    try:
        today = datetime.today().strftime("%d_%m_%Y")
        full_path = os.path.join(forecast.models_filepath, "optimizations/"+today+".pkl")
        if not os.path.exists(full_path):
            optimize(today=True)

        if not os.path.exists(full_path): return json.dumps("ERROR")

        optimization_db = joblib.load(full_path)

        graph_timestamps = optimization_db['timestamps']
        graph_optimization = optimization_db['total_balance']


        graph_df = pd.DataFrame({
            "hora": pd.to_datetime(graph_timestamps),
            "optimitzacio": graph_optimization,
            # "consum": graph_consum,
            # "generacio": graph_generation
        })
        graph_df['hora_str'] = graph_df['hora'].dt.strftime('%H:%M')

        fig = go.Figure()

        # Línia principal (verd amb fill)
        fig.add_trace(go.Scatter(
            x=graph_df["hora"],
            y=graph_df["optimitzacio"],
            mode='lines',
            name="Optimització",
            line=dict(color="green", width=2),
            fill='tozeroy',
            fillcolor="rgba(0,128,0,0.3)"
        ))

        now = datetime.now()

        fig.update_layout(
            height=400,
            yaxis=dict(zeroline=False),
            xaxis=dict(
                tickmode='array',
                tickvals=graph_timestamps,
                ticktext=graph_df['hora_str'],
                tickangle=-45,
                tickfont=dict(size=13),
                title="Hores"
            ),
            yaxis_title="Consum (W)",
            shapes=[
                dict(
                    type="line",
                    x0=now,
                    x1=now,
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    line=dict(color="red", width=2, dash="dash")
                )
            ],
            annotations=[
                dict(
                    x=now,
                    y=1.2,
                    xref="x",
                    yref="paper",
                    text="Actual",
                    showarrow=False,
                    font=dict(color="red", size=12),
                    textangle=-45
                )
            ],
        )

        fig_json = fig.to_plotly_json()
        response.content_type = "application/json"
        return json.dumps(fig_json, cls=plotly.utils.PlotlyJSONEncoder)

    except Exception as e:
        logger.exception(f"❌ Error obtenint scheduler': {e}")

@app.route('/get_flexi_data')
def get_global_flexi_data():
    """
    Obté les dades de la flexibilitat del dia actual per tal de generar una gràfica amb Plotly on mostri
    la flexibilitat global disponible per a cada hora.
    :return: figura Plotly codificada en json.dumps()
    """
    try:
        today = datetime.today().strftime("%d_%m_%Y")
        full_path = os.path.join(forecast.models_filepath, "optimizations/"+today+".pkl")
        if not os.path.exists(full_path):
            optimize(today=True)
        if not os.path.exists(full_path): return json.dumps("ERROR")

        optimization_db = joblib.load(full_path)

        graph_timestamps = optimization_db['timestamps']
        graph_optimization = optimization_db['total_balance']
        graph_fup = optimization_db['total_fup']
        graph_fdown = optimization_db['total_fdown']


        graph_df = pd.DataFrame({
            "hora": pd.to_datetime(graph_timestamps),
            "optimitzacio": graph_optimization,
            "fup": graph_fup,
            "fdown": graph_fdown,
        })
        graph_df['hora_str'] = graph_df['hora'].dt.strftime('%H:%M')

        fig = go.Figure()

        # Línia principal (verd amb fill)
        fig.add_trace(go.Scatter(
            x=graph_df["hora"],
            y=graph_df["optimitzacio"],
            mode='lines',
            name="Optimització",
            line=dict(color="green", width=2)
        ))

        fig.add_trace(go.Scatter(
            x=graph_df["hora"],
            y=graph_df["fup"],
            mode="lines+markers",
            name="Fup",
            line=dict(color="red"),
        ))

        fig.add_trace(go.Scatter(
            x=graph_df["hora"],
            y=graph_df["fdown"],
            name="Fdown",
            mode="lines+markers",
            line=dict(color="cyan"),
        ))

        now = datetime.now()

        fig.update_layout(
            height=400,
            yaxis=dict(zeroline=False),
            xaxis=dict(
                tickmode='array',
                tickvals=graph_timestamps,
                ticktext=graph_df['hora_str'],
                tickangle=-45,
                tickfont=dict(size=13),
                title="Hores"
            ),
            yaxis_title="Consum (W)",
            shapes=[
                dict(
                    type="line",
                    x0=now,
                    x1=now,
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    line=dict(color="red", width=2, dash="dash")
                )
            ]
        )

        fig_json = fig.to_plotly_json()
        response.content_type = "application/json"
        return json.dumps(fig_json, cls=plotly.utils.PlotlyJSONEncoder)

    except Exception as e:
        logger.exception(f"❌ Error obtenint scheduler': {e}")

@app.route('/get_device_config_and_state/<file_name>')
def get_device_config_and_state(file_name):
    """
    Mètode provisional amb únic proposit de debugar l'estat actual de la Sonnen vs el que hauria de fer segons l'optimització
    :param file_name:
    :return:
    """
    device_config = get_device_config_data(file_name)
    sonnen_state_sensor_id = device_config['device_config']['extra_vars']['percentatge_actual']['sensor_id']

    database.update_database(sonnen_state_sensor_id)
    database.clean_database_hourly_average(sensor_id=sonnen_state_sensor_id, all_sensors=False)

    start_time = device_config['device_config']['flexi_timestamps'][0]
    end_time = device_config['device_config']['flexi_timestamps'][-1]

    sonnen_state = database.get_all_saved_sensors_data(
        sensors_saved = [sonnen_state_sensor_id,] ,
        start_date = start_time,
        end_date = end_time
    )

    # Extraiem la llista de tuples per al sensor específic
    history = sonnen_state.get(sonnen_state_sensor_id, [])

    # Afegim al diccionari de resposta de forma estructurada
    device_config['device_config']['sonnen_history'] = {
        'x': [item[0] for item in history],  # Timestamps
        'y': [item[1] for item in history]  # Valors (%)
    }

    return device_config
#endregion PÀGINA MAIN

#region PÀGINA DEVICES

@app.get('/get_sensors')
def get_sensors():
    """
    Obté tota la informació disponible a la base de dades sobre cada un dels sensors.
    Separant la informació entre dispositiu pare i entitats fills.

    :return: diccionari amb dispositius pare i les seves entitats filles
    """
    try:
        all_devices_data = database.get_all_sensors_data()

        response.content_type = 'application/json'
        return json.dumps(all_devices_data)

    except Exception as ex:
        error_message = traceback.format_exc()
        return f"Error! Alguna cosa ha anat malament :c : {str(ex)}\nFull Traceback:\n{error_message}"

@app.route('/update_sensors', method='POST')
def update_sensors():
    """
    Actualitza les variables *save* i *type* de tots els sensors que han estat modificats al formulari.
    :return: Status: ok si tot ha anat bé, error en cas contrari.
    """
    data = request.json
    if not data:
        response.status = 400
        return {"status":"error", "msg": "Dades buides"}

    database.reset_all_sensors_save()

    for device in data:
        database.update_sensor_active(sensor = device['entityId'], active = True)

    return {"status": "ok", "msg": f"Sensors guardats"}

@app.route('/self_destruct', method='POST')
def self_destruct_database():
    """
    Elimina completament la base de dades SQL del programa
    :return: status: ok
    """
    database.self_destruct()
    return {"status": "ok"}

#endregion PÀGINA DEVICES

#region PÀGINA DATABASE

@app.route('/get_graph_info', method='POST')
def graphs_view():
    """
    Genera un diccionari amb les dates d'inici i final indicades per l'usuari i les dades
    dels sensors per a enviar al frontend i poder generar un plotly.

    :return: Diccionari {Status, Range{Start, End,Label}, Graphs{...,...,}}
    """
    try:
        selected_sensors = request.forms.get("sensors_id")
        selected_sensors_list = [sensor.strip() for sensor in selected_sensors.split(',')] if selected_sensors else []
        date_to_check = ''

        date_to_check_input = request.forms.getall("datetimes")
        if  not date_to_check_input:
            # Mostrar per defecte els últims 14 dies
            start_date = datetime.today() - timedelta(days=14)
            end_date = datetime.today()
            date_label = None
        else:
            date_to_check = date_to_check_input[0].split(' - ')
            start_date = datetime.strptime(date_to_check[0], '%d/%m/%Y %H:%M').strftime("%Y-%m-%dT%H:%M:%S") + '+00:00'
            end_date = datetime.strptime(date_to_check[1], '%d/%m/%Y %H:%M').strftime("%Y-%m-%dT%H:%M:%S") + '+00:00'
            date_label = date_to_check_input[0]


        sensors_data = database.get_all_saved_sensors_data(selected_sensors_list, start_date, end_date)

        response = {
            "status": "ok",
            "range":{
                "start": start_date,
                "end": end_date,
                "label": date_label,
            },
            "graphs": {}
        }

        if len(sensors_data) == 0:
            return json.dumps({
                "status": "empty",
                "message": "No hi ha dades disponibles",
                "graphs": {}
            })

        for sensor_id, records in sensors_data.items():
            timestamps = []
            values = []

            for ts, value in records:
                if value is not None:
                    timestamps.append(ts)
                    values.append(value)

            if not values:
                response["graphs"][sensor_id] = {
                    "status": "no-data",
                    "message": f"No hi ha dades del sensor {sensor_id}"
                }
                continue

            response["graphs"][sensor_id] = {
                "status": "ok",
                "timestamps": timestamps,
                "values": values
            }

        return json.dumps(response)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@app.route('/force_update_database')
def force_update_database():
    """
    Actua com a connexió entre en frontend (HTML) i la base de dades,
     cridant al mètode per a actualitzar les dades dels sensors.
    :return: "ok"
    """
    database.update_database("all")
    database.clean_database_hourly_average(all_sensors=True)
    return "ok"

#endregion PÀGINA DATABASE

#region PÀGINA MODEL

@app.route('/get_model_config/<model_name>')
def get_model_config(model_name):
    """
    Obté la configuració del model indicat
    :param model_name: Nom del model a obtenir
    :return: configuració del model *model_name* en format string.
    """
    try:
        model_path = os.path.join(forecast.models_filepath,'forecastings/',f"{model_name}.pkl")
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

@app.route('/get_model_metrics/<model_name>')
def get_model_metrics(model_name):
    """
    Obté les mètriques del model indicat.
    :param model_name: nom del model a obtenir
    :return: Diccionari amb Status(ok/error), metrics (mètriques del model) i train_val_test_split
    """
    try:
        model_path = os.path.join(forecast.models_filepath,'forecastings/',f"{model_name}.pkl")
        
        if not os.path.exists(model_path):
            return json.dumps({"status": "error", "message": "Model not found"})
        
        with open(model_path, 'rb') as f:
            model_db = joblib.load(f)
        
        metrics = model_db.get('metrics', {})
        train_val_test = model_db.get('train_val_test_split', {})
        
        # Convertir tipus NumPy/Pandas a tipus natius de Python
        metrics = convert_to_json_serializable(metrics)
        train_val_test = convert_to_json_serializable(train_val_test)
        
        response = {
            "status": "ok",
            "metrics": metrics,
            "train_val_test_split": train_val_test
        }
        
        return json.dumps(response)
    
    except Exception as e:
        logger.error(f"❌ Error getting metrics for model {model_name}: {e}")
        return json.dumps({"status": "error", "message": str(e)})

def train_model():
    """
    Entrena el model per a forecastings futurs
    :return: Model entrenat
    """
    form_data = {key: request.forms.get(key) for key in request.forms.keys()}
    return ForecasterManager.train_model(
        form_data=form_data,
        database=database,
        forecaster=forecast,
        lat=optimalScheduler.latitude,
        lon=optimalScheduler.longitude,
    )

def forecast_model(selected_forecast, today=True):
    """
    Realitza forecast a partir d'un model entrenat.
    :param selected_forecast: forecast a realitzar (model)
    :param today: True si realitzem un forecast a data d'avui, False si el realitzem amb data de demà
    :return: Forecasting realitzat.
    """
    ForecasterManager.forecast_model(
        selected_forecast=selected_forecast,
        database=database,
        models_filepath=forecast.models_filepath,
        today=today,
    )

def delete_model():
    """
    Elimina el model indicat al formulari.
    :return: None
    """
    selected_model = request.forms.get("models")
    ForecasterManager.delete_model(
        model_name=selected_model,
        database=database,
        models_filepath=forecast.models_filepath,
    )

@app.route('/submit-model', method="POST")
def submit_model():
    """
    Actua com a pont entre el frontent (HTML) de model.html i el backend.
     Cridant a la funció indicada segons el que ha seleccionat l'usuari (Entrentar, Forecasting o Eliminar model)
    :return: Pàgina model.html actualitzada.
    """
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

@app.route('/get_forecast_data/<model_name>')
def get_forecast_data(model_name):
    """
    Obté les dades del forecasting indicat *model_name*
    :param model_name: nom del model de forecasting del qual obtenir les dades.
    :return:
    - Status
    - Timestamps
    - Predictions
    - Valors reals
    - Timestamps dels valors reals
    - Predicció del dia anterior
    - Timestamps de la predicció del dia anterior
    - Timestamp inicial
    - Timestamp final
    """
    try:
        today_date = datetime.today().strftime('%d-%m-%Y')
        yesterday_date = (datetime.today() - timedelta(days = 1)).strftime('%d-%m-%Y')

        forecasts = database.get_data_from_forecast_from_date(model_name + ".pkl", today_date)
        yesterday = database.get_data_from_forecast_from_date(model_name + ".pkl", yesterday_date)

        if forecasts.empty:
            predictions = ""
            timestamps = ""
        else:
            timestamps = forecasts["timestamp"].tolist()
            predictions = forecasts["value"].tolist()

        if yesterday.empty:
            yesterday_predictions = ""
            yesterday_timestamps = ""
        else:
            yesterday_predictions = yesterday["value"].tolist()
            yesterday_timestamps = yesterday["timestamp"].tolist()



        real_values = []
        real_values_timestamps = []
        for i in range(len(forecasts['real_value'])):
            if not pd.isna(forecasts['real_value'][i]):
                real_values.append(forecasts['real_value'][i])
                real_values_timestamps.append(forecasts['timestamp'].tolist()[i])

        start_timestamp = (datetime.today() - timedelta(days=4)).replace(hour=0, minute=0).strftime('%Y-%m-%d %H:%M')
        last_timestamp = (datetime.today() + timedelta(days=4)).replace(hour=0, minute=0).strftime('%Y-%m-%d %H:%M')

        return json.dumps({
            "status": "ok",
            "timestamps": timestamps,
            "predictions": predictions,
            "real_values": real_values,
            "real_values_timestamps": real_values_timestamps,
            "yesterday_predictions": yesterday_predictions,
            "yesterday_timestamps": yesterday_timestamps,
            "start_timestamp": start_timestamp,
            "last_timestamp": last_timestamp,
        })


    except Exception as e:
        logger.error(f"❌ Error getting forecast for model {model_name}: {e}")
        return json.dumps({"status": "error", "message": str(e)})

#endregion PÀGINA MODEL

#region PÀGINA CONFIGURACIÓ
@app.post('/save_config')
def save_config():
    """
    Guarda la configuració d'usuari entrat al formulari. Generant claus privades per al Blockchain.
    :return: "OK"
    """
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
    """
    Elimina l'arxiu de configuració d'usuari guardat a /config/user.config"
    :return: String amb l'estat
    """
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
    """
    Obté el document .pkl on es guarden els últim 10 missatges enviats al Blockchain.
    :return: Diccionari amb status (OK / Error) i data que es troba dins el fitzer *res_certify.pkl*
    """
    try:
        full_path = os.path.join(forecast.models_filepath, "config", "res_certify.pkl")
        status = "ERROR"
        data = {}

        if os.path.exists(full_path):
            data = joblib.load(full_path)
            status = "OK"

        return json.dumps({
            "status": status,
            "data": data
        })

    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Error! : {str(e)}"

def get_user_configuration_data():
    """
    Obté la configuració de l'usuari guardada al document *config/user.config*
    :return: Informació guardada de l'usuari (nom, variable consum, variable generació, formulari bloquejat).
    """
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

    return user_data

#endregion PÀGINA CONFIGURACIÓ

#region PÀGINA OPTIMITZACIÓ

@app.route('/run_optimization')
def run_optimization():
    """
    Funció filtre que crida optimize amb paràmetre fixe de *today = True*
    :return: None
    """
    optimize(today=True)

@app.route('/optimize')
def optimize(today = False):
    """
    Realitza l'optimització per a la data indicada (Avui o demà).
    En cas que funcioni correctament guarda timestamps, balanç total, preu total i configuració dels dispositius a un document .pkl
    a amb nom *%d-%m-%YY* a la carpeta *share/exitos/optimizations/*
    :param today: Booleana. True si l'optimització és del dia d'avui, False en cas que sigui per l'endemà.
    :return:  None
    """
    try:
        horizon = 24
        horizon_min = 1 # 1 = 60 minuts  | 2 = 30 minuts | 4 = 15 minuts

        user_data = get_user_configuration_data()
        global_consumer_id = user_data['consumption']
        global_generator_id = user_data['generation']

        if global_generator_id == '' or global_consumer_id == '':
            logger.warning("⚠️ Variables globals no seleccionades a la configuració d'usuari.")
            return 'ERROR'

        price = []

        success, devices_config, price, total_balance_hourly = optimalScheduler.start_optimization(
            consumer_id = global_consumer_id,
            generator_id = global_generator_id,
            horizon = horizon,
            horizon_min = horizon_min,
            today = today)

        if success:
            # GUARDAR A FITXER
            optimization_result = {
                "timestamps": optimalScheduler.timestamps,
                "total_balance": total_balance_hourly,
                "total_price": price,
                "devices_config": devices_config
            }

            total_fup, total_fdown = flexibility(optimization_result)

            optimization_result["total_fup"] = total_fup
            optimization_result["total_fdown"] = total_fdown

            if today:
                save_date = datetime.today().strftime("%d_%m_%Y")
            else:
                save_date = (datetime.today() + timedelta(days=1)).strftime("%d_%m_%Y")
            full_path = os.path.join(forecast.models_filepath, "optimizations/"+save_date+".pkl")
            os.makedirs(forecast.models_filepath + 'optimizations', exist_ok=True)
            if os.path.exists(full_path):
                logger.warning("Eliminant arxiu antic d'optimització ")
                os.remove(full_path)

            joblib.dump(optimization_result, full_path)
            logger.info(f"✏️ Optimització diària guardada al fitxer {full_path}")

            #Configurar Scheduler
            schedule.clear('device_config_tasks')
            schedule.every().hour.at(":00").do(run_threaded, config_optimized_devices_HA).tag('device_config_tasks')
            logger.info("📅 Job programat per executar-se un cop cada hora (als minuts :00)")



    except Exception as e:
        logger.error(f"❌ Error optimitzant: {str(e)}: {traceback.format_exc()}")

@app.post('/get_config_file_names')
def get_config_file_names():
    """
    Obté els noms de tots els documents de configuració de dispositius guardats a *share/exitos/optimizations/configs/*
    :return: Diccionari {Status: ok / error, "names": [noms dels documents]
    """
    # CONFIGURACIONS CREADES
    created_configs_path = forecast.models_filepath + "/optimizations/configs"

    if os.path.exists(created_configs_path) and os.path.isdir(created_configs_path):
        json_config_files = [f for f in os.listdir(created_configs_path) if f.endswith(".json")]

        if len(json_config_files) == 0: return {"status": "error"}
        return {"status": "ok", "names" : json_config_files}
    else:
        return {"status": "error"}

@app.post('/save_optimization_config')
def save_optimization_config():
    """
    Guarda la configuració entrada al formulari (optimization page -> New Device) com a arxiu .json a la carpeta */share/exitos/optimizations/configs/* \n
    El nom de l'arxiu és el nom del dispositiu introduit. \n
    En cas que ja existeixi una configuració amb el mateix nom elimina la config existent i guarda la nova.\n
    :return: {status: ok / error, "msg": info de l'estat en format string}
    """
    data = request.json
    if not data:
        response.status = 400
        return {"status":"error", "msg": "Dades buides"}

    device_name = data.get("device_name")

    full_path = os.path.join(forecast.models_filepath, "optimizations/configs/"+ device_name +".json")
    os.makedirs(forecast.models_filepath + 'optimizations/configs', exist_ok=True)

    if os.path.exists(full_path):
        logger.warning(f"Eliminant arxiu antic de configuració {device_name}")
        os.remove(full_path)

    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    for var in data['extra_vars'].values():
        database.update_sensor_active(var['sensor_id'], True)


    return {"status": "ok", "msg": f"Optimització desada com {device_name}.json"}

@app.post('/delete_optimization_config/<file_name>')
def delete_optimization_config(file_name):
    """
    Elimina l'arxiu de configuració del device indicat per paràmetre.
    :param file_name: nom de l'arxiu que es vol eliminar.
    :return: {status: ok / error}
    """
    logger.debug(f"eliminant info {file_name}")
    full_path = os.path.join(forecast.models_filepath, "optimizations/configs/" + file_name)
    logger.debug(full_path)
    if os.path.exists(full_path):
        os.remove(full_path)
        return {"status": "ok"}
    else:
        return {"status": "error", "msg": "No existeix arxiu {file_name}.json"}

@app.route('/get_device_config_data/<file_name>')
def get_device_config_data(file_name):
    """
    Obté la configuració guardada al document indicat per paràmetre, guardat a */share/exitos/optimizations/configs/* \n

    :param file_name: Nom de l'arxiu que es vol obtenir.
    :return: {status: ok , device_config: { }} si ha anat bé, {status: error, msg: ""} en cas contrari
    """
    config_path = forecast.models_filepath + "/optimizations/configs/" + file_name
    device_config = {}

    if not os.path.exists(config_path):
        response.status = 400
        return {"status": "error", "msg": "Dades buides"}

    with open(config_path, 'r', encoding='utf-8') as f:
        device_config = json.load(f)
    
    today = datetime.today().strftime("%d_%m_%Y")
    device_config_path = os.path.join(forecast.models_filepath, "optimizations/" + today + ".pkl")
    if not os.path.exists(device_config_path):
        return {"status": "ok", "device_config": device_config}

    optimization_db = joblib.load(device_config_path)
    fixed_name = file_name.removesuffix(".json")
    device_config['hourly_config'] = optimization_db['devices_config'][fixed_name].tolist()
    device_config['timestamps'] = pd.to_datetime(optimization_db['timestamps']).strftime('%Hh').tolist()

    #OBTENIR FLEXIBILITAT
    flex_path = forecast.models_filepath + "flexibility/" + file_name
    if not os.path.exists(flex_path):
        return {"status": "ok", "device_config": device_config}

    with open(flex_path, 'r', encoding='utf-8') as f:
        flexi_data = json.load(f)

    device_config['f_up'] = flexi_data['f_up']
    device_config['f_down'] = flexi_data['f_down']
    device_config['flexi_timestamps'] = flexi_data['timestamps']

    return {"status": "ok", "device_config": device_config}

@app.route('/get_device_types/<locale>')
def get_device_types(locale='ca'):
    """
    Obté els tipus de Device del programa configurats a l'arxiu *optimization_devices.conf*\n
    :param locale: idioma del programa, per trobar l'arxiu en l'idioma configurat actualment.
    :return: {Tipus de dispositius guardats}
    """

    # Validar locale per evitar path traversal
    allowed_locales = ['ca', 'es', 'en']
    if locale not in allowed_locales:
        locale = 'ca'  # Default to Catalan

    config_path = f'resources/optimization_configs/optimization_devices_{locale}.conf'

    if not os.path.exists(config_path):
        logger.warning(f"⚠️ - No s'ha trobat el fitxer de configuració: {config_path}")
        # Fallback to default Catalan config
        config_path = 'resources/optimization_configs/optimization_devices_ca.conf'

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            devices_data = json.load(f)
        return devices_data  # Return dict directly, Bottle will serialize it
    except Exception as e:
        logger.error(f"Error carregant configuració de dispositius: {e}")
        return {}

@app.route('/update_device_config',method='POST')
def update_device_config():
    """
    Actualitza la configuració del dispositiu amb les noves dades entrades al formulari (només el paràmetre que indica si controlem o no el dispositiu)
    :return: {status: success / error}
    """
    data = request.json

    if not data:
        response.status = 400
        return {"error": "No s'han rebut dades"}

    device_name = data.get('device')
    new_status = data.get('status')

    file_path = os.path.join(forecast.models_filepath,"optimizations/configs/", device_name)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            device_config = json.load(f)

        device_config['controller_state'] = new_status

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(device_config, f, indent = 4)

        response.status = 200
        return {"status": "success"}
    except FileNotFoundError:
        response.status = 404
        logger.error("❌ ERROR: No s'ha trobat l'arxiu")
        return {"error": f"L'arxiu {device_name} no s'ha trobat."}
    except Exception as e:
        response.status = 500
        logger.error(f"❌ ERROR: {e}")
        return {"error": f"Error intern: {str(e)}"}



#endregion PÀGINA OPTIMITZACIÓ

#region FLEXIBILITY
def flexibility(optimization_db):
    """
    Calcula la flexibilitat de l'optimització realitzada.\n
    Cerca quin dispositiu s'ha optimitzat i delega el càlcul a la classe del dispositiu.
    Docu: Comentar funció quan estigui acabada
    """

    if optimization_db is None:
        return [], [], [], []

    all_devices = list(optimalScheduler.consumers.values()) + \
                  list(optimalScheduler.generators.values()) + \
                  list(optimalScheduler.energy_storages.values())

    # Variables per acumular resultats de flexibilitat totals
    total_fup = optimization_db['total_balance'].copy()
    total_fdown = optimization_db['total_balance'].copy()


    for device in all_devices:
        if device.name in optimization_db['devices_config']:
            try:
                result = device.get_flexibility(optimization_db)
                FlexibilityManager.get_flexibility(device_flex=result,
                                                   base_file_path=forecast.models_filepath,
                                                   total_fup=total_fup,
                                                   total_fdown=total_fdown,
                                                   device_name=device.name)
            except Exception as e:
                logger.error(f"❌ Error calculating flexibility for {device.name}: {e}")
                continue

    # Retornem els totals acumulats
    return total_fup, total_fdown

def daily_flex():
    """
    Docu: Comentar funció quan estigui acabada
    :return:
    """
    flexi_data = FlexibilityManager.send_flexibility(forecast.models_filepath)
    flexi_response = FlexibilityManager.generate_fake_response(flexi_data)
    logger.info(f"  📎{flexi_response['instructions_text'][0]}")

    FlexibilityManager.dispatch_local_devices(
        flexi_response['flexibility_profile_requested'], 
        forecast.models_filepath,
        optimalScheduler
    )


#endregion FLEXIBILITY

#region DAILY TASKS

def daily_task():
    """
    Funció que s'executa diariament per tal de realitzar els Forecasts i l'optimització.
    :return:
    """
    try:
        # Actualitzem la base de dades
        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        database.update_database("all")
        database.clean_database_hourly_average(all_sensors=True)

        # Si l'hora actual és anterior a les 20:00, l'objectiu és "avui".
        # Si és posterior, suposem que el procés s'està preparant per "demà".
        target_today = datetime.now().hour < 20
        
        #forecast
        daily_forecast_task(today=target_today)

        # Optimització
        logger.warning(f"📈 [{hora_actual}] - INICIANT PROCÉS D'OPTIMITZACIÓ")
        optimize(today=target_today)

    except Exception as e:
        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        logger.error(f" ❌ [{hora_actual}] - ERROR al daily task : {e}")

def daily_database_clean():
    """
    Funció que s'executa cada nit per tal de netejar la base de dades. \n
    Elimina de la base de dades *dades* tots aquells senosrs que tingui guardats però ja no estiguin marcats per a guardar.
    :return: None
    """
    try:
        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        logger.info(f"📂 [{hora_actual}] - INICIANT PROCÉS DE NETEJA DE LA BASE DE DADES")

        sensors_id = database.get_all_sensors()
        sensors_id = sensors_id['entity_id'].tolist()

        for sensor_id in sensors_id:
            is_active = database.get_sensor_active(sensor_id)
            if not is_active:
                has_data = database.get_data_from_sensor(sensor_id)
                if len(has_data) > 0:
                    logger.debug(f"     ▫️ Eliminant dades del sensor {sensor_id}")
                    database.remove_sensor_data(sensor_id)


        logger.info(f"📂 [{hora_actual}] - BASE DE DADES NETA")

    except Exception as e:
        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        logger.error(f" ❌ [{hora_actual}] - ERROR al monthly task : {e}")

def daily_forecast_task(today=False):
    """
    Funció que es crida diariament a la nit per tal de realitzar els forecastings de tots els models guardats.
    :param today: True si es vol fer el forecasting a data d'avui, False en cas que sigui per l'endamà
    :return: None
    """
    try:
        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        logger.warning(f"📈 [Forecast] [{hora_actual}] - STARTING DAILY FORECASTING")

        models_saved = [os.path.basename(f) for f in glob.glob(forecast.models_filepath + "forecastings/*.pkl")]
        logger.info(f"   🧩 [Forecast] Models trobats per processar: {models_saved}")

        if not models_saved:
            logger.warning("   ⚠️ [Forecast] No s'han trobat models .pkl per al forecast automàtic!")
            return

        for model in models_saved:
            model_path = os.path.join(forecast.models_filepath, "forecastings/", model)
            try:
                with open(model_path, 'rb') as f:
                    config = joblib.load(f)
                aux = config.get('algorithm', '')
                if aux == '':
                    logger.warning(f"⚠️ [{model}] no té 'algorithm' definit, s'omet.")
                    continue
                logger.warning(f"   📊 Running daily forecast for {model}")
                forecast_model(model, today=today)
                logger.warning(f"   ✅ Forecast completat per {model}")
            except Exception as e_model:
                # Error per model individual — no atura la resta de models
                logger.error(f"   ❌ [Forecast] Error al forecast de {model}: {e_model}", exc_info=True)

        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        logger.warning(f"📈 [Forecast] [{hora_actual}] - ENDING DAILY FORECASTS")

    except Exception as e:
        hora_actual = datetime.now().strftime('%Y-%m-%d %H:00')
        logger.error(f"❌ [Forecast] [{hora_actual}] - ERROR general al daily forecast: {e}", exc_info=True)

def certificate_hourly_task():
    """
    Funció que es crida horariament. Envia amb Blockchain el consum i la generació de l'usuari d'aquella hora al sevidor de la comunitat.
    :return: None
    """
    try:
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
                database.clean_database_hourly_average(sensor_id=generation, all_sensors=False)
                generation_data = database.get_latest_data_from_sensor(sensor_id=generation)
                generation_timestamp = to_datetime(generation_data[0]).strftime("%Y-%m-%d %H:%M")
                generation_value = generation_data[1]
            else:
                logger.warning(f"⚠️ Recorda seleccionar el sensor de Generació i marcar-lo a l'apartat 'Sensors' per a guardar.")
                generation_timestamp = None
                generation_value = None

            if database.get_sensor_active(consumption) == 1 and consumption != 'None':
                database.update_database(consumption)
                database.clean_database_hourly_average(sensor_id=consumption, all_sensors=False)
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

        else:
            logger.warning(f"Encara no t'has unit a cap comunitat! \n"
                        f"Recorda completar la teva configuració d'usuari des de l'apartat 'configuració' de la pàgina")
    except Exception as e:
        logger.error(f" ❌ [{datetime.now().strftime('%d:%m:%Y %H:%m')}] - ERROR sending hourly task: {e}")

def config_optimized_devices_HA():
    """
    Configura els dispositius que han estat optimitzats al valor que tocaria cada hora per tal que segueixin el planing de l'optimització.\n
    S'executa cada hora.
    :return: None
    """
    try:
        if (optimalScheduler.consumers == {} and
                optimalScheduler.generators == {} and
                optimalScheduler.energy_storages == {}):
            optimalScheduler.prepare_data_for_optimization()


        today = datetime.today().strftime("%d_%m_%Y")
        full_path = os.path.join(forecast.models_filepath, "optimizations/"+ today +".pkl")
        
        if not os.path.exists(full_path):
            can_optimize = optimize(today=True)
            if can_optimize == "Empty": return

        current_date = datetime.now(tzlocal.get_localzone())
        logger.info(f"📆 [{current_date.strftime('%d-%b-%Y   %X')} ] Configurant dispositius H.A.")

        optimization_db = joblib.load(full_path)

        current_hour = datetime.now().hour

        collections = [
            optimalScheduler.consumers.values(),
            optimalScheduler.generators.values(),
            optimalScheduler.energy_storages.values()
        ]
        for collection in collections:
            for item in collection:
                file_path = os.path.join(forecast.models_filepath, "optimizations/configs/", f"{item.name}.json")
                with open(file_path, 'r', encoding='utf-8') as f:
                    device_config = json.load(f)

                if device_config['controller_state']:
                    value, sensor_id, sensor_type = item.controla(config = optimization_db['devices_config'][item.name], current_hour = current_hour)
                    # logger.debug(f"Sensor_ID: {sensor_id}, Value: {value}, SensorType: {sensor_type}")
                    database.set_sensor_value_HA(sensor_type, sensor_id, value)


    except Exception as e:
        logger.error(f"❌ [{datetime.now().strftime('%d:%m:%Y %H:%m')}] -  Error configurant horariament un dispositiu a H.A {e}")

def run_threaded(job_func):
    """
    Executa un thread secundari per no parar el programa en cas de fallada.
    """
    job_thread = threading.Thread(target=job_func)
    job_thread.start()

schedule.every().day.at("23:30").do(run_threaded, daily_task)
schedule.every().day.at("02:00").do(run_threaded, daily_database_clean)
schedule.every().hour.at(":00").do(run_threaded, certificate_hourly_task)

def run_scheduled_tasks():
    logger.debug("🗓️ SCHEDULER STARTED")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            # Això evita que el thread mori si una tasca falla
            logger.error(f"❌ Error en l'execució d'una tasca: {e}", exc_info=True)
        time.sleep(1)

scheduler_thread = threading.Thread(target=run_scheduled_tasks, daemon=True)
scheduler_thread.start()

#endregion DAILY TASKS

#region DEBUG REGION
@app.route('/panik_function')
def panik_function():
    "sensor.solarnet_potencia_fotovoltaica"
    # aux = database.get_latest_data_from_sensor("sensor.solarnet_potencia_fotovoltaica")
    # logger.info(aux)
    daily_database_clean()

#endregion DEBUG REGION

#region LLM
def register_llm_tools():
    """Registra totes les eines (tools) disponibles per al motor LLM."""
    if not hasattr(llm_engine.llm_engine, 'register_tool'):
        logger.warning("❌ No puc registrar eines: register_tool no trobat")
        return

    llm_engine.llm_engine.register_tool(
        name="get_current_time",
        func=tool_get_current_time,
        description="Obté la data i hora actuals del sistema.",
        parameters={
            "type": "object",
            "properties": {
                "dummy": {
                    "type": "string",
                    "description": "Ignoring this"
                }
            },
            "required": []
        }
    )

    llm_engine.llm_engine.register_tool(
        name="get_sensor_value",
        func=tool_get_sensor_value,
        description="Obté l'últim valor registrat d'un sensor específic (ex: sensor.bateria_soc).",
        parameters={
            "type": "object",
            "properties": {
                "sensor_id": {
                    "type": "string",
                    "description": "L'identificador del sensor (entity_id)."
                }
            },
            "required": ["sensor_id"]
        }
    )

    llm_engine.llm_engine.register_tool(
        name="get_current_day",
        func=tool_get_current_day,
        description="Obté la data d'avui (dia, mes i any).",
        parameters={
            "type": "object",
            "properties": {
                "dummy": {
                    "type": "string",
                    "description": "Ignoring this"
                }
            },
            "required": []
        }
    )

    llm_engine.llm_engine.register_tool(
        name="get_current_year",
        func=tool_get_current_year,
        description="Obté l'any en el que estem.",
        parameters={
            "type": "object",
            "properties": {
                "dummy": {
                    "type": "string",
                    "description": "Ignoring this"
                }
            },
            "required": []
        }
    )

    llm_engine.llm_engine.register_tool(
        name="get_optimization_configs",
        func=tool_get_optimization_configs,
        description=(
            "Obté totes les configuracions d'optimització de dispositius que l'usuari té guardades. "
            "Inclou el nom del dispositiu, el tipus, les restriccions (ex: capacitat màxima de la bateria) "
            "i les variables de mesura i control associades. "
            "Utilitza aquesta eina quan l'usuari pregunti per les seves configuracions actuals, "
            "vulgui saber quins dispositius té configurats, o necessiti consells sobre optimització energètica."
        ),
        parameters={
            "type": "object",
            "properties": {
                "config_name": {
                    "type": "string",
                    "description": "Opcional. Si saps el nom del dispositiu, posa'l aquí. Si no, deixa-ho en blanc per llistar-los tots."
                }
            },
            "required": []
        }
    )

    llm_engine.llm_engine.register_tool(
        name="get_system_entities",
        func=tool_get_system_entities,
        description=(
            "Llista els dispositius reals i les seves entitats (sensors i actuadors) disponibles al sistema Home Assistant. "
            "Aquesta llista reflecteix exactament el que l'usuari veu a la pantalla de 'Configuració de Dispositius'. "
            "Utilitza aquesta eina quan l'usuari pregunti 'quins dispositius tinc', 'busca el sensor de la rentadora', "
            "o quan vulguis ajudar a configurar un nou dispositiu d'optimització i necessitis saber l'ID real de l'entitat."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Opcional. Paraula clau per filtrar dispositius o entitats (ex: 'placa', 'bateria', 'shelly')."
                }
            },
            "required": []
        }
    )

    llm_engine.llm_engine.register_tool(
        name="get_available_device_types",
        func=tool_get_available_device_types,
        description=(
            "Obté tots els tipus de dispositius disponibles per configurar a l'optimitzador, "
            "incloent les seves restriccions (paràmetres a definir, com capacitat màxima) i variables "
            "(sensors de mesura i actuadors de control). "
            "Utilitza aquesta eina quan l'usuari vulgui saber quines opcions té per configurar un nou dispositiu, "
            "o quan necessitis entendre les opcions disponibles per fer una recomanació de configuració."
        ),
        parameters={
            "type": "object",
            "properties": {
                "device_type_id": {
                    "type": "string",
                    "description": "Opcional. Si saps el tipus exacte de dispositiu, posa'l aquí. Si no, deixa-ho en blanc per llistar-los tots."
                }
            },
            "required": []
        }
    )

#endregion LLM

#region Threading
from bottle import ServerAdapter
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn

class NoLogRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass # Silencia els logs HTTP

class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

class ThreadedServer(ServerAdapter):
    def run(self, handler):
        # Silencia els logs HTTP sempre (quiet de Bottle no arriba a l'adaptador)
        server = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer, handler_class=NoLogRequestHandler)
        server.serve_forever()

#endregion Threading

# Funció main que encén el servidor web.
def main():
    """
    Funció main que encén el servidor web.
    :return:  None
    """
    run(app=app, host=HOSTNAME, port=PORT, quiet=True, server=ThreadedServer)


# Executem la funció main
if __name__ == "__main__":
    logger.info("🌳 ExitOS Iniciat")

    # Inicialitzar rutes LLM i registrar eines
    try:
        llm_engine.init_routes(app, logger)
        register_llm_tools()
    except Exception as e:
        logger.error(f"❌ Error inicialitzant LLM: {e}")

    main()
    
