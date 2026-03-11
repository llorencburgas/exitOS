import os
import json
import joblib
import random

import numpy as np
import pandas as pd

from datetime import datetime, timedelta
from logging_config import setup_logger


logger = setup_logger()

#TODO: moure a un fitxer utilities (juntament amb la mateixa funció del server.py)
def convert_to_json_serializable(obj):
    """
    Converteix recursivament objectes amb tipus NumPy/Pandas a tipus natius de Python
    per permetre la serialització JSON.
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

def get_flexibility(device_flex,base_file_path, total_fup, total_fdown, device_name):
    if device_flex:
        fup, fdown, power, timestamps = device_flex

        # Guardem resultats individuals
        # Convertim timestamps a string per a JSON
        timestamps_str = [str(t) for t in timestamps]

        flexi_result = {
            "f_up": convert_to_json_serializable(fup),
            "f_down": convert_to_json_serializable(fdown),
            "power": convert_to_json_serializable(power),
            "timestamps": timestamps_str
        }

        full_path = os.path.join(base_file_path, "flexibility/" + device_name + ".json")
        os.makedirs(base_file_path + 'flexibility', exist_ok=True)

        if os.path.exists(full_path):
            logger.warning(f"Eliminant arxiu antic de flexibilitat ->  {device_name}")
            os.remove(full_path)

        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(flexi_result, f, indent=4)

        logger.info(f"✏️ Flexibilitat de {device_name} guardada al fitxer {full_path}")

        for i in range(len(total_fup)):
            total_fup[i] += fup[i]
            total_fdown[i] += fdown[i]

def send_flexibility(base_file_path, today=True):
    if today:
        save_date = datetime.today().strftime("%d_%m_%Y")
    else:
        save_date = (datetime.today() + timedelta(days=1)).strftime("%d_%m_%Y")
    full_path = os.path.join(base_file_path, "optimizations/" + save_date + ".pkl")
    optimization_db = joblib.load(full_path)

    data_to_send = {
        "consumption": optimization_db["total_balance"],
        "f_up": optimization_db["total_fup"],
        "f_down": optimization_db["total_fdown"],
        #posar restriccions
    }


    logger.warning("📎 ENVIANT INFORMACIÓ FLEXIBILITAT (simulat)")
    return data_to_send

def generate_fake_response(flexi_data):
    """
    Simula el servidor central. Retorna, com a màxim, UNA sola instrucció al dia.
    """
    logger.warning("📎 REBENT INFO FLEXIBILITAT (simulat)")

    baseline_consumption = flexi_data["consumption"]
    f_up = flexi_data["f_up"]
    f_down = flexi_data["f_down"]
    num_hours = len(baseline_consumption)

    requested_flex = [0.0] * num_hours
    instructions = []

    # 1. ESCENARI "NO FACIS RES": 30% de probabilitat que la xarxa estigui bé
    if random.random() < 0.30:
        return {
            "status": "success",
            "flexibility_profile_requested": requested_flex,
            "instructions_text": ["Tot correcte avui. No es requereix cap acció de flexibilitat."],
            "new_target_profile": [int(v) for v in baseline_consumption]
        }

    # Si passem d'aquí, la xarxa necessita ajuda.
    # 2. Triem a l'atzar QUIN problema hi ha avui: 50% Excés Solar, 50% Pic de Demanda
    event_type = random.choice(["solar", "peak"])

    hour_selected = None

    if event_type == "solar":
        # Busquem totes les hores entre les 11h i les 14h on ofereixis flexibilitat
        valid_hours = [h for h in range(11, 15) if h < num_hours and f_up[h] > 0]

        if valid_hours:
            # Triem UNA SOLA hora a l'atzar d'entre les vàlides
            hour_selected = random.choice(valid_hours)
            demand = int(random.uniform(0.5, 1.0) * f_up[hour_selected])
            requested_flex[hour_selected] = demand
            instructions.append(f"A les {hour_selected}h: +{demand}W (Aprofita l'excés solar)")

    elif event_type == "peak":
        # Busquem totes les hores entre les 18h i les 21h on ofereixis flexibilitat (f_down negatiu)
        valid_hours = [h for h in range(18, 22) if h < num_hours and f_down[h] < 0]

        if valid_hours:
            # Triem UNA SOLA hora a l'atzar d'entre les vàlides
            hour_selected = random.choice(valid_hours)
            capacitat_reduccio = abs(f_down[hour_selected])
            reduction = int(random.uniform(0.6, 1.0) * capacitat_reduccio)
            requested_flex[hour_selected] = -reduction
            instructions.append(f"A les {hour_selected}h: -{reduction}W (Redueix pel pic de demanda)")

    # Si la xarxa necessitava ajuda però no tenies flexibilitat en el tipus d'esdeveniment triat
    if hour_selected is None:
        instructions.append(
            "Es necessitava ajuda, però la casa no oferia flexibilitat per a l'esdeveniment d'avui.")

    response_from_server = {
        "status": "success",
        "flexibility_profile_requested": requested_flex,
        "instructions_text": instructions,
        "new_target_profile": [
            int(baseline_consumption[i] + requested_flex[i]) for i in range(num_hours)
        ]
    }

    return response_from_server


def load_flexibility_data(folder_path):
    """
    Llegeix tots els fitxers JSON de la carpeta especificada i crea un diccionari
    amb la flexibilitat de tots els dispositius.
    """
    devices_db = {}

    # Llistem tots els arxius de la carpeta, ordenats alfabèticament
    # (Veure nota sobre prioritats a sota)
    full_path = os.path.join(folder_path, "flexibility/" )
    files = sorted(os.listdir(full_path))

    for filename in files:
        if filename.endswith(".json"):
            # Traiem el".json" per tenir el nom net del dispositiu
            device_name = filename.replace(".json", "")
            file_path = os.path.join(full_path, filename)

            # Obrim i llegim el JSON
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    device_data = json.load(file)
                    # Guardem les dades al nostre diccionari general
                    devices_db[device_name] = device_data
            except Exception as e:
                print(f"Error llegint l'arxiu {filename}: {e}")

    return devices_db

def dispatch_devices(requested_flex, folder_path):
    """
    Llegeix els JSONs i reparteix la flexibilitat demanada.
    """

    # 1. Carreguem les dades de la carpeta
    devices_db = load_flexibility_data(folder_path)

    # 2. Fem el repartiment (mateixa lògica que abans)
    dispatch_plan = {}

    for hour in range(len(requested_flex)):
        req = requested_flex[hour]
        if req == 0:
            continue

        hour_plan = {}

        if req > 0:  # Augmentar consum
            remaining_to_allocate = req
            for device_name, device_info in devices_db.items():
                available_fup = device_info.get("f_up", [0] * 24)[hour]
                if available_fup > 0 and remaining_to_allocate > 0:
                    allocated = min(remaining_to_allocate, available_fup)
                    hour_plan[device_name] = allocated
                    remaining_to_allocate -= allocated

        elif req < 0:  # Reduir consum
            remaining_to_reduce = abs(req)
            for device_name, device_info in devices_db.items():
                available_fdown = device_info.get("f_down", [0] * 24)[hour]
                if available_fdown > 0 and remaining_to_reduce > 0:
                    allocated = min(remaining_to_reduce, available_fdown)
                    hour_plan[device_name] = -allocated
                    remaining_to_reduce -= allocated

        if hour_plan:
            dispatch_plan[device_name] = np.copy(device_info['power'])
            dispatch_plan[device_name][hour] = hour_plan[device_name]
        else:
            dispatch_plan = "No hi ha flex disponible"

    return dispatch_plan

# --- EXEMPLE D'ÚS ---
# requested_flex = [0, 0, 0, ... 1500, ...] (La llista de 24h que ens dona el servidor)
# carpeta = "/config/flexibilitat/" # La ruta on tinguis els JSON a Home Assistant

# pla = dispatch_devices(requested_flex, carpeta)
# print(pla)