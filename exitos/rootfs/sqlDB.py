import os
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd
import requests
from narwhals import String
from requests import get
from datetime import datetime, timedelta, timezone
import logging
import json
from typing import Optional, List, Dict, Any
import tzlocal



logger = logging.getLogger("exitOS")


class SqlDB():
    # region PRIVATE METHODS

    def __init__(self):
        """
        Constructor de la classe SqlDB. \n
        Inicialitza les variables necessàries de la classe i crea la Base de dades en cas que aquesta no existeixi.
        """
        self.running_in_ha = "HASSIO_TOKEN" in os.environ
        self.database_file = "share/exitos/dades.db" if self.running_in_ha else "dades.db"
        self.config_path = "share/exitos/user_info.conf" if self.running_in_ha else "user_info.config"
        self.supervisor_token = os.environ.get('SUPERVISOR_TOKEN', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI5YzMxMjU1MzQ0NGY0YTg5YjU5NzQ5NWM0ODI2ZmNhZiIsImlhdCI6MTc0MTE3NzM4NSwiZXhwIjoyMDU2NTM3Mzg1fQ.5-ST2_WQNJ4XRwlgHK0fX8P6DnEoCyEKEoeuJwl-dkE')
        self.base_url = "http://supervisor/core/api/" if self.running_in_ha else "http://margarita.udg.edu:28932/api/"
        self.headers = {
            "Authorization": f"Bearer {self.supervisor_token}",
            "Content-Type": "application/json"
        }

        if self.running_in_ha:
            self.base_filepath = "share/exitos/"
        else:
            self.base_filepath = "./share/exitos/"

        self.devices_info = self.get_devices_info()

        # comprovem si la Base de Dades existeix
        if not os.path.isfile(self.database_file):
            logger.info("La base de dades no existeix Creant-la...")
            self._init_db()

    def _init_db(self):
        """
        Crea les taules de la base de dades \n
        - DADES: conté els valors i timestamps de les dades \n
        - SENSORS: conté la info dels sensors
        - FORECASTS: conté les dades i timestamps de les prediccions realitzades per a cada model
        """

        logger.info("Iniciant creaciÃ³ de la Base de Dades")
        with sqlite3.connect(self.database_file, timeout=60.0) as con:
            cur = con.cursor()

            #creant les taules
            cur.execute("CREATE TABLE IF NOT EXISTS dades(sensor_id TEXT, timestamp NUMERIC, value)")
            cur.execute("CREATE TABLE IF NOT EXISTS sensors(sensor_id TEXT,friendly_name TEXT, units TEXT, parent_device TEXT, update_sensor BINARY, save_sensor BINARY)")
            cur.execute("CREATE TABLE IF NOT EXISTS forecasts(forecast_name TEXT, sensor_forecasted TEXT, forecast_run_time NUMERIC, forecasted_time NUMERIC, predicted_value REAL, real_value REAL)")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_dades_sensor_id_timestamp ON dades(sensor_id, timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id ON sensors(sensor_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forecasts_forecast_name ON forecasts(forecast_name)")

            con.commit()
        logger.info("Base de dades creada correctament.")

        self.update_database("all")
        self.clean_database_hourly_average(all_sensors=True)

    def _get_connection(self):
        """
        Crea una connexió amb la base de dades indicada a la varaible *self.database_file*
        :return: Connexió amb la base de dades
        """
        return sqlite3.connect(self.database_file, timeout=60.0)

    def self_destruct(self):
        """
        Elimina completament tota la base de dades
        :return: None
        """
        with sqlite3.connect("dades.db", timeout=60.0) as con:
            cur = con.cursor()
            cur.execute("DROP TABLE IF EXISTS dades")
            cur.execute("DROP TABLE IF EXISTS sensors")
            cur.execute("DROP TABLE IF EXISTS forecasts")
            con.commit()
        self._init_db()

    def query_select(self, table:str, column:str, sensor_id: str, con = None) -> List[Any]:
        """
        Executa un query SQL bàsic a la base de dades
        :param table: nom de la taula a la que es vol accedir
        :param column: nom de la columna a la qual es col accedir
        :param sensor_id: nom del sensor concret que es vol buscar
        :param con: connexió amb la base de dades creada
        :return:
        """

        close_con = False
        if con is None:
            con = self._get_connection()
            close_con = True

        cur = con.cursor()
        cur.execute(f"SELECT {column} FROM {table} WHERE sensor_id = ?", (sensor_id,))
        result = cur.fetchone()
        cur.close()

        if close_con: con.close()

        return result

    # endregion

    # region SENSORS - Getters
    def get_all_sensors(self) -> Optional[pd.DataFrame]:
        """
        Obté una llista amb el ID i Friendly Name de tots els sensors
        :return: [[ID, FriendlyName], [ID, FriendlyName], ...] - **None** si no troba l'API
        """
        response = get(f"{self.base_url}states", headers=self.headers)
        if response.ok:
            sensors_list = pd.json_normalize(response.json())
            if 'entity_id' in sensors_list.columns:
                return sensors_list[['entity_id', 'attributes.friendly_name']]
        return None

    def get_current_sensor_state(self, sensor_id: str):
        """
        Obté l'estat actual del sensor indicat (valor actual)
        :param sensor_id: ID del sensor que volem obtenir
        :return: Valor actual del sensor que marca l'API
        """
        response = get(f"{self.base_url}states/{sensor_id}", headers=self.headers)
        if response.ok:
            aux = pd.json_normalize(response.json())
            return aux['state']
        return None

    def get_all_sensors_data(self):
        """
        Obté informació de tots els devices i entitats guardats a la base de dades.
        :return: {"device_name": ,"entities": {{"entity_id","entity_name","save","type"},...}}
        """
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("select * from sensors")
            rows = cur.fetchall()

            grouped = {}

            for row in rows:
                entity_id = row[0]
                friendly_name = row[1] or ""
                device_name = row[3] or "Unknown"
                save = row[5]
                sensor_type = row[6]

                if device_name not in grouped:
                    grouped[device_name] = []

                grouped[device_name].append({
                    "entity_id": entity_id,
                    "entity_name": friendly_name,
                    "save": save,
                    "type": sensor_type,
                })

            result = [
                {
                    "device_name": device,
                    "entities": entities
                }
                for device, entities in grouped.items()
            ]

        return result

    def get_data_from_sensor(self, sensor_id: str) -> pd.DataFrame:
        """
        Obté tots els valors guardats del sensor indicat juntament amb el seu timestamp, ordenats per Timestamp.
        :param sensor_id: ID del sensor del qual es volen obtenir les dades
        :return: Pandas DataFrame [timestamp, value] - *Exemple de Valors*: [2025-11-24 03:00:00+00:00, 621.06893]
        """
        query = """SELECT timestamp, value FROM dades WHERE sensor_id = ? """
        con = self._get_connection()
        df = pd.read_sql_query(query, con, params=(sensor_id,))
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
        con.close()
        return df.sort_values('timestamp').reset_index(drop=True)

    def get_all_saved_sensors_data(self, sensors_saved: List[str], start_date: str, end_date: str) -> Dict[str, List[tuple]]:
        """
        Obté totes les dades guardades dins un rang de dades per tots els sensors indicats.
        :param sensors_saved: ID dels sensors dels quals es volen obtenir les dades
        :param start_date: Data d'inici de les dades
        :param end_date: Data final per a les dades
        :return: Diccionari amb les dades per a cada sensor { ID_sensor_1: [(timestamp, value), (timestamp,value)], ID_sensor_2: ... } - *Exemple de Valors*: ('2026-04-22T12:00:00', 2727.2727272727275)
        """

        # Normalitzem el format de les dates per assegurar que coincideixen amb la "T" de la DB
        # Això converteix "2026-04-28 23:00:00" en "2026-04-28T23:00:00"
        start_date_iso = start_date.replace(" ", "T")
        end_date_iso = end_date.replace(" ", "T")

        sensors_data: Dict[str, List[tuple]] = {sensor_id: [] for sensor_id in sensors_saved}
        with self._get_connection() as con:
            placeholders = ', '.join(['?'] * len(sensors_saved))
            query = f"""
                SELECT sensor_id, timestamp, value
                FROM dades
                WHERE sensor_id IN ({placeholders})
                AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            """

            # Preparem els paràmetres: primer la llista de sensors, després les dues dates
            params = sensors_saved + [start_date_iso, end_date_iso]

            cursor = con.execute(query, params)

            # Omplim el diccionari directament mentre recorrem els resultats
            for sensor_id, timestamp, value in cursor.fetchall():
                sensors_data[sensor_id].append((timestamp, value))

        return sensors_data

    def get_all_saved_sensors_id(self, kw: bool = False) -> List[str]:
        """
        Obté el ID de tots els sensors marcats per a guardar.
        :param kw: Si és true, retorna només aquells sensors que usen KW com a unitat de mesura. En cas que no s'indiqui és False, mostrarà tots els ID guardats
        :return: ['ID_sensor1', 'ID_sensor2']
        """

        query = "SELECT sensor_id FROM sensors WHERE units IN ('W', 'kW')" if kw else "SELECT sensor_id FROM sensors WHERE save_sensor = 1"
        with self._get_connection() as con:
            return [row[0] for row in con.execute(query).fetchall()]

    def get_sensor_active(self, sensor: str) -> int:
        """
        Obté 0 o 1 segons si el sensor indicat es troba actiu o no (és a dir que està marcat per a guardar dades)
        :param sensor: ID del sensor a obtenir
        :return: 0 si no està actiu, 1 en cas contrari (actiu = guarda dades)
        """
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT save_sensor FROM sensors WHERE sensor_id = ?", (sensor,))
            result = cur.fetchone()
            return result[0] if result else 0

    def get_latest_data_from_sensor(self, sensor_id):
        """
        Obté l'última dada guardada, juntament amb el timestamp, del sensor indicat.
        :param sensor_id: ID del sensor del qual es vol obtenir la dada.
        :return: ('timestamp', 'value') - *Exemple de Valors*: ('2026-04-29T07:00:00', 411.07975460122697)
        """
        with self._get_connection() as con:
            cursor = con.cursor()
            cursor.execute(""" SELECT timestamp, value 
                               FROM dades 
                               WHERE sensor_id = ? 
                               ORDER BY timestamp DESC
                                LIMIT 1""", (sensor_id,))
            aux = cursor.fetchone()
            cursor.close()
            return aux

    # endregion

    # region SENSORS - Setters

    def reset_all_sensors_save(self):
        """
        Reinicia el paràmetre *save_sensor* de tots els sensors, posant-lo a 0
        :return: None
        """
        with self._get_connection() as con:
            con.execute("UPDATE sensors SET save_sensor = 0")

    def update_sensor_active(self, sensor: str, active: bool):
        """
        Actualitza la variable *save_sensor* del sensor indicat
        :param sensor: ID del sensor que es vol modificar
        :param active: nou estat a guardar (Boolean)
        :return: None
        """
        with self._get_connection() as con:
            con.execute("UPDATE sensors SET save_sensor = ? WHERE sensor_id = ?", (int(active), sensor))
            con.commit()

    def remove_sensor_data(self, sensor_id: str):
        """
        Elimina totes les entrades d'un sensor de la taula *dades* de la base de dades
        :param sensor_id: ID del sensor que es vol eliminar.
        :return: None
        """
        with self._get_connection() as con:
            con.execute("DELETE FROM dades WHERE sensor_id = ?", (sensor_id,))
            con.commit()

    def update_database(self, sensor_to_update):
        """
        Actualitza la taula *dades* de la base de dades, posant totes les noves dades dels sensors marcats ocm actius. En cas que s'indiqui un sensor només s'actualitzarà aquest.
        :param sensor_to_update: "all" si es vol actualitzar tota la base de dades, sensor_id en cas que es vulgui actualitzar només un sensor concret
        :return: None
        """
        all_sensors_debug = False
        #obtenim la llista de sensors de la API
        if sensor_to_update == "all":
            sensors_list = pd.json_normalize(
                get(self.base_url + "states", headers=self.headers).json()
            )
            all_sensors_debug = True
        else:
            sensors_list = pd.json_normalize(
                get(self.base_url + "states/" + sensor_to_update, headers=self.headers).json()
            )
            if len(sensors_list) == 0:
                logger.error("❌ No existeix un sensor amb l'ID indicat")
                return None

        if all_sensors_debug:
            logger.info("🗃️ Iniciant l'actualització de la base de dades...")

        local_tz = tzlocal.get_localzone()  # Gets system local timezone (e.g., 'Europe/Paris')
        current_date = datetime.now(local_tz)
        devices = self.get_devices_info()

        with self._get_connection() as con:
            for j in sensors_list.index:
                sensor_id = sensors_list.iloc[j]["entity_id"]
                parent_device = self.get_parent_device_from_sensor_id(sensor_id, devices)

                if parent_device == "None":
                    continue

                sensor_info = self.query_select("sensors", "*", sensor_id, con)

                #si no hem obtingut cap sensor ( Ã©s a dir, no existeix a la nosta BD)
                if sensor_info is None:
                    cur = con.cursor()
                    columns = [col[1] for col in cur.execute("PRAGMA table_info(sensors)")]

                    values_to_insert = (
                        sensor_id,
                        sensors_list.iloc[j]['attributes.friendly_name'],
                        sensors_list.iloc[j]["attributes.unit_of_measurement"],
                        True,
                        False,
                        parent_device,
                    )
                    cur.execute(
                        "INSERT INTO sensors (sensor_id,friendly_name, units, update_sensor, save_sensor, parent_device) VALUES (?,?,?,?,?,?)",
                        values_to_insert
                    )
                    cur.close()
                    con.commit()
                    logger.debug(f"     [ {current_date.strftime('%d-%b-%Y   %X')} ] Afegit un nou sensor a la base de dades: {sensor_id}")
                else: #TODO: Quan tots els usuaris ja no tinguin sensor_type dins sensors eliminar aquest ELSE
                    cur = con.cursor()

                    cur.execute("PRAGMA table_info(sensors)")
                    columns = [col[1] for col in cur.fetchall()]

                    if 'sensor_type' in columns:
                        cur.execute("ALTER TABLE sensors DROP COLUMN sensor_type")
                        logger.debug(f"Columna 'sensor_type' eliminada de la base de dades SENSORS")

                    cur.close()
                    con.commit()

                save_sensor = self.query_select("sensors","save_sensor", sensor_id, con)[0]
                update_sensor = self.query_select("sensors","update_sensor", sensor_id, con)[0]

                if save_sensor and update_sensor:
                    logger.debug(f"     [ {current_date.strftime('%d-%b-%Y   %X')} ] Actualitzant sensor: {sensor_id}")

                    last_date_saved = self.query_select("dades","timestamp, value", sensor_id, con)
                    if last_date_saved is None:
                        start_time = current_date - timedelta(days=21)
                        last_value = []
                    else:
                        last_date_saved, last_value = last_date_saved
                        start_time = datetime.fromisoformat(last_date_saved)

                    while start_time <= current_date:
                        end_time = start_time + timedelta(days = 7)

                        string_start_date = start_time.strftime('%Y-%m-%dT%H:%M:%S')
                        string_end_date = end_time.strftime('%Y-%m-%dT%H:%M:%S')

                        url = (
                            self.base_url + "history/period/" + string_start_date +
                            "?end_time=" + string_end_date +
                            "&filter_entity_id=" + sensor_id
                            + "&minimal_response&no_attributes"
                        )



                        response = get(url, headers=self.headers)
                        if response.status_code == 200:
                            try:
                                sensor_data_historic = pd.json_normalize(response.json())
                            except ValueError as e:
                                logger.error(f"          Error parsing JSON: {str(e)}")
                                sensor_data_historic = pd.DataFrame()
                        elif response.status_code == 500:
                            logger.critical(f"          Server error (500): Internal server error at sensor {sensor_id}")
                            sensor_data_historic = pd.DataFrame()
                        else:
                            logger.error(f"          Request failed with status code: {response.status_code}")
                            sensor_data_historic = pd.DataFrame()

                        #actualitzem el valor obtingut de l'històric del sensor
                        cur = con.cursor()
                        for column in sensor_data_historic.columns:
                            value = sensor_data_historic[column][0]['state']

                            #mirem si el valor és vàlid
                            if value == 'unknown' or value == 'unavailable' or value == '':
                                value = np.nan
                            if last_value != value:
                                last_value = value
                                time_stamp = sensor_data_historic[column][0]['last_changed']

                                cur.execute(
                                    "INSERT INTO dades (sensor_id, timestamp, value) VALUES (?,?,?)",
                                        (sensor_id, time_stamp, value))

                        cur.close()
                        con.commit()
                        start_time += timedelta(days = 7)

        if all_sensors_debug:
            logger.info(f"🗃️ [ {current_date.strftime('%d-%b-%Y   %X')} ] TOTS ELS SENSORS HAN ESTAT ACTUALITZATS")

    # endregion

    # region SENSORS - Home Asistant
    def set_sensor_value_HA(self, sensor_mode, sensor_id, value):
        """
        Força l'estat indicat a value, al dispositiu **sensor_id** a través de l'API de Home Assistant.
        :param sensor_mode: Tipus de sensor que es vol modificar (select, number, button, switch).
        :param sensor_id: ID del sensor que es vol controlar.
        :param value: Nou valor a aplicar al sensor.
        :return: None
        """
        if sensor_mode == 'select':
            url = f"{self.base_url}services/select/select_option"
            data = {'entity_id': sensor_id,
                    'option': value}
        elif sensor_mode == 'number':
            url = f"{self.base_url}services/number/set_value"
            data = {'entity_id': sensor_id, "value": value}
        elif sensor_mode == 'button':
            url = f"{self.base_url}services/button/press"
            data = {'entity_id': sensor_id}
        elif sensor_mode == 'switch':
            url = f"{self.base_url}services/switch/turn_on"
            data = {'entity_id': sensor_id}

        response = requests.post(url, headers=self.headers, json=data)

        logger.info(f"resposta {sensor_id}: {response.status_code} - {response.text}")

    # endregion

    # region FORECASTS
    def get_forecasts_name(self):
        """
        Obté el nom de tots els forecastings guardats a la base de dades.
        :return: [ ('forecasting1', ), ('forecasting2', )]
        """
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT DISTINCT forecast_name FROM forecasts")
            aux = cur.fetchall()
            cur.close()
        return aux

    def get_data_from_forecast_from_date(self, forecast_id, date):
        """
        Obté les dades (temps de realització del forecast, temps predit, valor predit i valor real) del forecast indicat per a la data desitjada.
        :param forecast_id: ID del forecast del qual es volen obtenir les dades.
        :param date: Data de la qual es volen obtenir les dades ('%d-%m-%Y')
        :return: Data Frame ['run_date', 'timestamp', 'value', 'real_value']
        """
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                    SELECT forecast_run_time, forecasted_time, predicted_value, real_value
                    FROM forecasts
                    WHERE forecast_name = ?
                    AND forecast_run_time = ?
                """, (forecast_id, date))
            aux = cur.fetchall()
            cur.close()
            data = pd.DataFrame(aux, columns=('run_date','timestamp', 'value', 'real_value'))
        return data

    def get_data_from_forecast_from_date_and_sensorID(self, sensor_id, date):
        """
        Obté el forecast realitzat per a un sensor concret en la data indicada.
        :param sensor_id: ID del sensor del qual es volen trobar forecastings
        :param date: Data sobre la qual es vol trobar forecasting
        :return: Data Frame ['run_date', 'timestmap', 'value', 'real_value']
        """
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                        SELECT forecast_run_time, forecasted_time, predicted_value, real_value
                        FROM forecasts
                        WHERE sensor_forecasted = ?
                          AND forecast_run_time = ?
                        """, (sensor_id, date))
            aux = cur.fetchall()
            cur.close()
            data = pd.DataFrame(aux, columns=('run_date', 'timestamp', 'value', 'real_value'))
        return data

    def remove_forecast(self, forecast_id):
        """
        Elimina el forecasting amb ID indicat de la base de dades, eliminant totes les entrades amb aquell ID
        :param forecast_id: ID del forecast que es vol eliminar.
        """
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM forecasts WHERE forecast_name = ?",(forecast_id,))
            con.commit()
            cur.close()

    def save_forecast(self, data):
        """
        Guarda el forecasting realitzat a la base de daes. En cas que existeixi un forecasting realitzat a la mateixa data el substitueix eliminant l'antic.
        :param data: dades del forecating, han d'incloure (forecast_name, sensor_forecasted, forecast_run_time, forecasted_time,
                                                            predicted_value, real_value)
        """
        forecast_name = data[0][0]
        forecast_run_time = data[0][2]

        with self._get_connection() as con:
            cur = con.cursor()

            # eliminem forecast amb mateix data i nom per evitar duplicats en un sol dia
            cur.execute("""
                        DELETE
                        FROM forecasts
                        WHERE forecast_name = ?
                          AND forecast_run_time = ?
                        """, (forecast_name, forecast_run_time))

            # inserim el nou forecast
            cur.executemany("""
                            INSERT INTO forecasts (forecast_name, sensor_forecasted, forecast_run_time, forecasted_time,
                                                   predicted_value, real_value)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """, data)

            con.commit()
            cur.close()

    # endregion

    # region GENERAL
    def vacuum(self):
        """
        Allibera l'espai no utilitzat i reconstrueix el fitxer de la base de dades.\n
        Aquest mètode executa la comanda VACUUM per defragmentar la base de dades, reduir-ne la mida al disc i optimitzar el rendiment de les consultes futures.
        """
        with self._get_connection() as con:
            con.execute("VACUUM")

    def clean_database_hourly_average(self, sensor_id=None, all_sensors=True):
        """
        Agrupa i compacta les dades històriques (últims 21 dies) per hores.
        Calcula la mitjana aritmètica per a valors numèrics o la moda per a valors de text, substituint els registres originals per un únic resum horari per optimitzar l'espai.

        :param sensor_id: Identificador del sensor si es processa de forma individual.
        :param all_sensors: Si és True, ignora sensor_id i processa tota la base de dades.
        """

        if all_sensors: logger.info(f"🧹 INICIANT NETEJA TOTAL")
        with self._get_connection() as con:
            cur = con.cursor()
            if all_sensors:
                sensor_ids = [row[0] for row in con.execute("SELECT DISTINCT sensor_id FROM dades").fetchall()]
            else:
                if not sensor_id:
                    logger.warning("⚠️ S'ha demanat neteja individual però no s'ha passat sensor_id.")
                    return
                sensor_ids = [sensor_id]

            if not sensor_ids:
                logger.error("❌ No s'han trobat sensors per processar.")
                return

            limit_date = (datetime.now() - timedelta(days=21)).isoformat()

            for sensor_id in sensor_ids:
                if all_sensors:
                    logger.debug(f"      Processant neteja sensor: {sensor_id}")
                else:
                    current_date = datetime.now(tzlocal.get_localzone())
                    logger.info(f"🧹 [{current_date.strftime('%d-%b-%Y   %X')}] - Neteja sensor {sensor_id}")
                df = pd.read_sql_query(
                    f"SELECT timestamp, value FROM dades WHERE sensor_id = ? AND timestamp >= ?", con,
                    params=(sensor_id, limit_date)
                )

                if df.empty:
                    continue

                # 1. Convertim a datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
                # li treiem la zona horària per poder operar
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
                # Si després de la conversió el dataframe s'ha quedat buit o hi ha massa NaT,
                # ATUREM el procés abans de fer el DELETE de la base de dades.
                if df['timestamp'].isna().all():
                    logger.error(
                        f"❌ ERROR: Totes les dates del sensor {sensor_id} han fallat al convertir-se. Avortant neteja per no perdre dades.")
                    continue

                # 2. Ara sí, arrodonim a l'hora
                df['hour'] = df['timestamp'].dt.floor('h')

                # 3. Procés de dades (Numèric vs Text)
                numeric_values = pd.to_numeric(df['value'], errors='coerce')
                is_numeric = numeric_values.notna().any()

                if is_numeric:
                    df['value'] = numeric_values
                    df_grouped = df.groupby('hour', as_index=False)['value'].mean()
                else:
                    # Per a text (com "Charging"), agafem la moda
                    df_grouped = df.groupby('hour', as_index=False)['value'].agg(
                        lambda x: x.mode().iloc[0] if not x.mode().empty else None
                    )

                try:
                    # Netegem l'antic
                    con.execute("DELETE FROM dades WHERE sensor_id = ? AND timestamp >= ?", (sensor_id, limit_date))

                    # Preparem la inserció amb un format ISO net i sense microsegons
                    rows_to_insert = [
                        (sensor_id, row['hour'].strftime('%Y-%m-%dT%H:%M:%S'),
                         None if pd.isna(row['value']) else row['value'])
                        for _, row in df_grouped.iterrows()
                    ]

                    con.executemany(
                        "INSERT INTO dades (sensor_id, timestamp, value) VALUES (?, ?, ?)", rows_to_insert
                    )
                    con.commit()
                except Exception as e:
                    con.rollback()
                    logger.error(f"❌ Error processant {sensor_id}: {e}")

        if all_sensors: logger.info("🧹 NETEJA FINALITZADA")
        self.vacuum()

    def get_lat_long(self):
        """
        Obté les coordenades geogràfiques de la configuració de Home Assistant.

        Realitza una petició a l'endpoint de configuració i n'extreu la latitud i la longitud.
        En cas d'error o de no trobar les claus necessàries, registra la incidència.

        :return: Una tupla "latitude, longitude" si té èxit, un enter -1 si no troba les columnes, o un string amb el missatge d'error en cas d'excepció.
        """
        try:
            response = get(self.base_url + "config", headers=self.headers)
            config = pd.json_normalize(response.json())

            if 'latitude' in config.columns and 'longitude' in config.columns:
                latitude = config['latitude'][0]
                longitude = config['longitude'][0]

                return latitude, longitude
            else:
                logger.error("Could not found the data in the response file")
                logger.info(f"Available columns: {config.columns.tolist()}")

                return -1
        except Exception as e:
            return f"Error! : {str(e)}"


    # endregion

    # region DEVICES
    def get_devices_info(self):
        """
        Recupera l'estructura completa de dispositius i entitats de Home Assistant.

        Envia un template de Jinja2 a l'API per agrupar les entitats segons el seu
        dispositiu associat, incloent-hi els atributs 'friendly_name' i gestionant
        les entitats sense dispositiu assignat sota un grup especial anomenat '0rphans'.

        :return: Una llista de diccionaris amb el nom del dispositiu i les seves entitats,
                 o un diccionari buit en cas d'error en la petició. [
                {
                "device_name": "Sensor Temperatura",
                "entities": [
                  {
                    "entity_id": "sensor.temp_living",
                    "entity_name": "Temperatura Salo"
                  }
                ]
                },
                {
                "device_name": "0rphans",
                "entities": [
                  {
                    "entity_id": "sun.sun",
                    "entity_name": "Sol"
                  }
                ]
                }
                ]
        """
        url = f"{self.base_url}template"
        template = """
            {% set _ = now() %}
            
            {% set orphan_name = "0rphans" %}
            {% set devices = states | map(attribute='entity_id') | map('device_id') | unique | reject('eq', None) | list %}
            {% set ns = namespace(devices = []) %}
            
            {# DEVICES NORMALS #}
            {% for device in devices %}
                {% set name = device_attr(device, 'name') or device %}
                {% set ents = device_entities(device) or [] %}
                {% set info = namespace(entities = []) %}
            
                {% for entity in ents %}
                    {% if not entity.startswith('update.') %}
                        {% set friendly = state_attr(entity, 'friendly_name') or '' %}
                        {% set info.entities = info.entities + [{
                            "entity_id": entity,
                            "entity_name": friendly
                        }] %}
                    {% endif %}
                {% endfor %}
            
                {% if info.entities %}
                    {% set ns.devices = ns.devices + [{
                        "device_name": name,
                        "entities": info.entities
                    }] %}
                {% endif %}
            {% endfor %}
            
            {# ENTITATS SENSE DEVICE #}
            {% set orphan = namespace(entities = []) %}
            
            {% for st in states %}
                {% set eid = st.entity_id %}
                {% if device_id(eid) is none and not eid.startswith('update.') %}
                    {% set friendly = state_attr(eid, 'friendly_name') or '' %}
                    {% set orphan.entities = orphan.entities + [{
                        "entity_id": eid,
                        "entity_name": friendly
                    }] %}
                {% endif %}
            {% endfor %}
            
            {% set ns.devices = ns.devices + [{
                "device_name": orphan_name,
                "entities": orphan.entities
            }] %}
            
            {{ ns.devices | tojson }}
        """

        response = requests.post(url, headers=self.headers, json = {"template": template})

        if response.status_code == 200:
            # json_response = response.json()
            full_devices = response.text.strip()
            result = json.loads(full_devices)
            return result
        else:
            logger.error(f"❌ Error en la resposta: {response.status_code}")
            logger.debug(f"▫️ Cos resposta:\n     {response.text}")
            return {}

    def get_parent_device_from_sensor_id(self, sensor_id: str, devices_dict) -> str:
        """
        Cerca el nom del dispositiu pare al qual pertany una entitat concreta.

        :param sensor_id: L'identificador de l'entitat a cercar.
        :param devices_dict: El diccionari de dispositius obtingut amb 'get_devices_info'.
        :return: El nom del dispositiu pare o "None" si no es troba la coincidència.
        """
        for device in devices_dict:
            for entity in device['entities']:
                if entity['entity_id'] == sensor_id:
                    return device['device_name']

        return "None"


    # endregion


