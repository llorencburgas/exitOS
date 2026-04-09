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
    Simula el servidor central. Retorna UNA sola instrucció al dia,
    aplicada a un RANG horari continu (ex: de 11h a 14h).
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
    event_type = random.choice(["solar", "peak"])
    event_assigned = False

    # Triem una durada per al bloc (entre 2 i 4 hores de petició)
    durada_bloc = random.choice([2, 3, 4])

    if event_type == "solar":
        # Definim on pot començar el bloc (ex: entre les 10h i les 13h)
        start_h = random.randint(10, 13)
        end_h = min(start_h + durada_bloc, 16)  # Evitem que passi de les 16h

        # Mirem quanta flexibilitat positiva (f_up) oferia la casa en aquestes hores en concret
        capacitats_disponibles = [f_up[h] for h in range(start_h, end_h) if h < num_hours and f_up[h] > 0]

        if capacitats_disponibles:
            # El servidor demana un valor basant-se en la mitjana del que la casa oferia en aquest bloc
            mitjana_flex = sum(capacitats_disponibles) / len(capacitats_disponibles)
            demand = int(random.uniform(0.5, 1.0) * mitjana_flex)

            # Apliquem la mateixa petició a totes les hores del rang
            for h in range(start_h, end_h):
                requested_flex[h] = demand

            instructions.append(f"De {start_h}h a {end_h}h: +{demand}W (Aprofita l'excés solar)")
            event_assigned = True

    elif event_type == "peak":
        # Definim on pot començar el bloc de tarda/vespre (ex: entre les 18h i les 20h)
        start_h = random.randint(18, 20)
        end_h = min(start_h + durada_bloc, 23)

        # Mirem quanta flexibilitat negativa (f_down) oferia la casa
        capacitats_disponibles = [abs(f_down[h]) for h in range(start_h, end_h) if h < num_hours and f_down[h] < 0]

        if capacitats_disponibles:
            mitjana_flex = sum(capacitats_disponibles) / len(capacitats_disponibles)
            reduction = int(random.uniform(0.6, 1.0) * mitjana_flex)

            for h in range(start_h, end_h):
                requested_flex[h] = -reduction

            instructions.append(f"De {start_h}h a {end_h}h: -{reduction}W (Redueix pel pic de demanda)")
            event_assigned = True

    # Si l'esdeveniment no s'ha pogut assignar perquè just en aquelles hores no hi havia res de flexibilitat
    if not event_assigned:
        instructions.append(
            "Es necessitava ajuda per blocs, però la casa no oferia cap flexibilitat en la franja requerida."
        )

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

def dispatch_local_devices(requested_flex, folder_path, optimal_scheduler):
    """
    Intenta complir la petició del servidor combinant dispositius hora a hora.
    Calcula si hem aconseguit l'objectiu o ens hem quedat curts.
    Ara evalua els límits globals seqüencials utilitzant l'estat intern seqüencial
    dels dispositius.
    """
    
    # 1. Carreguem les dades de l'optimització base d'avui
    today = datetime.today().strftime("%d_%m_%Y")
    optimization_db_path = os.path.join(folder_path, "optimizations", f"{today}.pkl")
    
    if os.path.exists(optimization_db_path):
        optimization_db = joblib.load(optimization_db_path)
    else:
        optimization_db = {"devices_config": {}}
        
    # Recollim tots els dispositius actius instanciats
    active_devices = (
        list(optimal_scheduler.consumers.values()) + 
        list(optimal_scheduler.generators.values()) + 
        list(optimal_scheduler.energy_storages.values())
    )
    
    # 2. Inicialitzem el tracker de flexibilitat per cada dispositiu
    # (aquí preparen la seva còpia interna del pla per fer l'avaluació seqüencial)
    for device in active_devices:
        baseline_plan = optimization_db.get("devices_config", {}).get(device.name, [0]*24)
        device.initialize_flex_tracker(baseline_plan)

    dispatch_plan = {}
    compliance_report = {}  # Guardarem com de bé hem complert l'objectiu

    for hour in range(len(requested_flex)):
        req = requested_flex[hour]
        if req == 0:
            continue

        hour_plan = {}
        remaining_to_allocate = req

        # Iterem sobre els dispositius demanant-los quanta flexibilitat poden aportar
        for device in active_devices:
            if remaining_to_allocate == 0:
                break
                
            allocated = device.reserve_flexibility(hour, remaining_to_allocate)
            if allocated != 0:
                hour_plan[device.name] = allocated
                remaining_to_allocate -= allocated

        # Guardem si hem complert l'objectiu o ens ha faltat potència
        compliance_report[hour] = {
            "demanat": req,
            "aconseguit": req - remaining_to_allocate,
            "falta": remaining_to_allocate
        }

        if hour_plan:
            dispatch_plan[hour] = hour_plan

    return dispatch_plan, compliance_report
