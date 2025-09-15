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
from typing import Optional, List, Dict, Any
import tzlocal



logger = logging.getLogger("exitOS")


class SqlDB():
    def __init__(self):
        """
        Constructor de la classe. \n
        Crea la connexió a la base de dades
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

        #comprovem si la Base de Dades existeix
        if not os.path.isfile(self.database_file):
            logger.info("La base de dades no existeix Creant-la...")
            self._init_db()

    def _init_db(self):
        """
        Crea les taules de la base de dades \n
            -> DADES: conté els valors i timestamps de les dades \n
            -> SENSORS: conté la info dels sensors
            -> FORECASTS: conté les dades i timestamps de les prediccions realitzades per a cada model
        """

        logger.info("Iniciant creació de la Base de Dades")
        with sqlite3.connect(self.database_file) as con:
            cur = con.cursor()

            #creant les taules
            cur.execute("CREATE TABLE IF NOT EXISTS dades(sensor_id TEXT, timestamp NUMERIC, value)")
            cur.execute("CREATE TABLE IF NOT EXISTS sensors(sensor_id TEXT, units TEXT, update_sensor BINARY, save_sensor BINARY, sensor_type TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS forecasts(forecast_name TEXT, sensor_forecasted TEXT, forecast_run_time NUMERIC, forecasted_time NUMERIC, predicted_value REAL, real_value REAL)")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_dades_sensor_id_timestamp ON dades(sensor_id, timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id ON sensors(sensor_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forecasts_forecast_name ON forecasts(forecast_name)")

            con.commit()
        logger.info("Base de dades creada correctament.")

        self.update_database("all")
        self.clean_database_hourly_average()

    def _get_connection(self):
        return sqlite3.connect(self.database_file)

    def query_select(self, table:str, column:str, sensor_id: str, con = None) -> List[Any]:
        """
        Executa una query SQL a la base de dades
        """
        if con is None: con = self._get_connection()

        cur = con.cursor()
        cur.execute(f"SELECT {column} FROM {table} WHERE sensor_id = ?", (sensor_id,))
        result = cur.fetchone()
        cur.close()
        return result

    def get_all_sensors(self) -> Optional[pd.DataFrame]:
        response = get(f"{self.base_url}states", headers=self.headers)
        if response.ok:
            sensors_list = pd.json_normalize(response.json())
            if 'entity_id' in sensors_list.columns:
                return sensors_list[['entity_id', 'attributes.friendly_name']]
        return None

    def clean_sensors_db(self):
        logger.debug("Iniciant neteja de la Base de Dades de Sensors")
        all_sensors = self.get_all_sensors()
        if all_sensors is None:
            logger.warning("No s'ha pogut obtenir la llista de sensors.")
            return

        all_sensors_list = set(all_sensors['entity_id'].tolist())

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("select sensor_id from sensors")
            sensors_in_db = {row[0] for row in cur.fetchall()}

            deleted = 0
            for sensor_id in sensors_in_db - all_sensors_list:
                cur.execute("DELETE FROM sensors WHERE sensor_id = ?", (sensor_id,))
                logger.debug(f"··· Eliminant sensor {sensor_id} ···")
                deleted += 1
            con.commit()

        logger.debug(f"La base de dades creada correctament. {deleted} sensors eliminats.")
        self.vacuum()

    def get_sensors_save(self, sensors: List[str]) -> List[Any]:
        results = []
        with self._get_connection() as con:
            for sensor_id in sensors:
                res = self.query_select("sensors", "save_sensor", sensor_id, con)
                results.append(res[0] if res else 0)

        return results

    def get_sensors_type(self, sensors: List[str]) -> List[Any]:
        results = []
        with self._get_connection() as con:
            for sensor_id in sensors:
                res = self.query_select("sensors", "sensor_type", sensor_id, con)
                results.append(res[0] if res else 0)
        return results

    def get_all_saved_sensors_data(self, sensors_saved: List[str], start_date: str, end_date: str) -> Dict[str, List[tuple]]:
        data: List[tuple] = []
        with self._get_connection() as con:
            cur = con.cursor()
            for sensor_id in sensors_saved:
                cur.execute("""
                SELECT sensor_id, timestamp, value
                FROM dades
                WHERE sensor_id = ?
                AND timestamp BETWEEN ? AND ?
                """, (sensor_id, start_date, end_date))
                data.extend(cur.fetchall())

        sensors_data: Dict[str, List[tuple]] = {}
        for sensor_id, timestamp, value in data:
            if sensor_id not in sensors_data:
                sensors_data[sensor_id] = []
            sensors_data[sensor_id].append((timestamp, value))

        return sensors_data

    def get_data_from_sensor(self, sensor_id: str) -> pd.DataFrame:
        query = """SELECT timestamp, value FROM dades WHERE sensor_id = ? """
        df = pd.read_sql_query(query, self._get_connection(), params=(sensor_id,))
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
        return df.sort_values('timestamp').reset_index(drop=True)

    def get_all_saved_sensors_id(self, kw: bool = False) -> List[str]:

        query = "SELECT sensor_id FROM sensors WHERE units IN ('W', 'kW')" if kw else "SELECT sensor_id FROM sensors WHERE save_sensor = 1"
        with self._get_connection() as con:
            return [row[0] for row in con.execute(query).fetchall()]

    def update_sensor_active(self, sensor: str, active: bool):
        with self._get_connection() as con:
            con.execute("UPDATE sensors SET save_sensor = ? WHERE sensor_id = ?", (int(active), sensor))
            con.commit()

    def update_sensor_type(self, sensor: str, new_type: str):
        with self._get_connection() as con:
            con.execute("UPDATE sensors SET sensor_type = ? WHERE sensor_id = ?", (new_type, sensor))
            con.commit()

    def get_sensor_active(self, sensor: str) -> int:
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT save_sensor FROM sensors WHERE sensor_id = ?", (sensor,))
            result = cur.fetchone()
            return result[0] if result else 0

    def remove_sensor_data(self, sensor_id: str):
        with self._get_connection() as con:
            con.execute("DELETE FROM dades WHERE sensor_id = ?", (sensor_id,))
            con.commit()

    def clean_database_hourly_average(self):
        logger.info("🧹 INICIANT NETEJA DE LA BASE DE DADES")
        with self._get_connection() as con:
            # Comprovar si la taula 'dades' està buida
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM dades")
            count = cur.fetchone()[0]
            if count == 0:
                logger.info("❗La base de dades està buida. No s'executa la neteja.")
                return
            cur.close()

            sensor_ids = [row[0] for row in con.execute("SELECT DISTINCT sensor_id FROM dades").fetchall()]

            limit_date = (datetime.now() - timedelta(days=21)).isoformat()

            for sensor_id in sensor_ids:
                logger.debug(f"      Processant sensor: {sensor_id}")
                df = pd.read_sql_query(
                    f"SELECT timestamp, value FROM dades WHERE sensor_id = ? AND timestamp >= ?", con, params=(sensor_id,limit_date)
                )
                if df.empty:
                    logger.info(f"           ❌ No hi ha dades per al sensor {sensor_id} dins el període. S'omet.")
                    continue

                df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', errors='coerce')
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                df['hour'] = df['timestamp'].dt.floor('h')

                #Agrupem horariament, mantenint NaN si no hi ha valors vàlids
                df_grouped = df.groupby('hour', as_index=False)['value'].mean()

                con.execute("DELETE FROM dades WHERE sensor_id = ? AND timestamp >= ?", (sensor_id, limit_date))

                rows_to_insert = [
                    (sensor_id, row['hour'].isoformat(), None if pd.isna(row['value']) else row['value'])
                    for _, row in df_grouped.iterrows()
                ]
                con.executemany(
                    "INSERT INTO dades (sensor_id, timestamp, value) VALUES (?, ?, ?)", rows_to_insert
                )
                con.commit()
        logger.info("🧹 NETEJA COMPLETADA")
        self.vacuum()

    def update_database(self, sensor_to_update):
        """
        Actualitza la base de dades amb la API del Home Assistant.
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

        with self._get_connection() as con:
            for j in sensors_list.index:
                sensor_id = sensors_list.iloc[j]["entity_id"]

                sensor_info = self.query_select("sensors", "*", sensor_id, con)

                #si no hem obtingut cap sensor ( és a dir, no existeix a la nosta BD)
                if sensor_info is None:
                    cur = con.cursor()
                    values_to_insert = (
                        sensor_id,
                        sensors_list.iloc[j]["attributes.unit_of_measurement"],
                        True,
                        False,
                        "None"
                    )
                    cur.execute(
                        "INSERT INTO sensors (sensor_id, units, update_sensor, save_sensor, sensor_type) VALUES (?,?,?,?,?)",
                        values_to_insert
                    )
                    cur.close()
                    con.commit()
                    logger.debug(f"     [ {current_date.strftime('%d-%b-%Y   %X')} ] Afegit un nou sensor a la base de dades: {sensor_id}")
                else : #TODO: ELIMINAR QUAN TOTS ELS USUARIS TINGUIN LA TAULA FORECAST ACTUALITZADA
                    cur = con.cursor()
                    cur.execute("PRAGMA table_info(forecasts)")
                    columns = [col[1] for col in cur.fetchall()]
                    if 'sensor_forecasted' not in columns:
                        cur.execute("ALTER TABLE forecasts ADD COLUMN sensor_forecasted TEXT")
                        logger.debug(f"Columna 'sensor_forecasted' afegida a la base de dades: {sensor_id}")
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

    def get_lat_long(self):
        """
        Retorna la lat i long del home assistant
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

    def save_forecast(self, data):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.executemany("""
                INSERT INTO forecasts (forecast_name, sensor_forecasted, forecast_run_time, forecasted_time, predicted_value, real_value) 
                VALUES (?,?,?,?,?,?)
            """, data)

            con.commit()
            cur.close()

    def get_forecasts_name(self):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT DISTINCT forecast_name FROM forecasts")
            aux = cur.fetchall()
            cur.close()
        return aux

    def get_data_from_latest_forecast(self, forecast_id):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                    SELECT forecast_run_time, forecasted_time, predicted_value, real_value
                    FROM forecasts
                    WHERE forecast_name = ?
                    AND forecast_run_time = (
                        SELECT MAX(forecast_run_time)
                        FROM forecasts
                        WHERE forecast_name = ?
                    )
                """, (forecast_id, forecast_id))
            aux = cur.fetchall()
            cur.close()
            data = pd.DataFrame(aux, columns=('run_date','timestamp', 'value', 'real_value'))
        return data

    def get_data_from_latest_forecast_from_sensorid(self, sensor_id):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
                    SELECT forecasted_time, predicted_value, real_value
                    FROM forecasts
                    WHERE sensor_forecasted = ?
                    AND forecast_run_time = (
                        SELECT MAX(forecast_run_time)
                        FROM forecasts
                        WHERE sensor_forecasted = ?
                    )
                """, (sensor_id, sensor_id))
            aux = cur.fetchall()
            cur.close()
            data = pd.DataFrame(aux, columns=('timestamp', 'value', 'real_value'))
        return data

    def remove_forecast(self, forecast_id):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM forecasts WHERE forecast_name = ?",(forecast_id,))
            con.commit()
            cur.close()

    def vacuum(self):
        with self._get_connection() as con:
            con.execute("VACUUM")

    def get_active_sensors_by_type(self, sensor_type: String = 'consum'):
        #TODO: mirar si posar una booleana per indicar tipus d'unitats (Kw) del sensor
        with self._get_connection() as con:
            cursor = con.cursor()

            cursor.execute("""
                SELECT sensor_id FROM sensors WHERE save_sensor = 1 AND sensor_type = ?
                """, (sensor_type,)
            )
            sensors = cursor.fetchall()

            resultat = {}
            for sensor in sensors:
                cursor.execute("""
                    SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM dades WHERE sensor_id = ?
                """, (sensor[0],))

                fila = cursor.fetchone()
                min_ts, max_ts, total_valors = fila

                if min_ts and max_ts:
                    min_dt = datetime.fromisoformat(min_ts)
                    max_dt = datetime.fromisoformat(max_ts)
                    total_hores = int((max_dt - min_dt).total_seconds() //3600) + 1

                    # Obtenim dies actius (format YYYY-MM-DD)
                    cursor.execute("""
                                   SELECT DISTINCT DATE (timestamp)
                                   FROM dades
                                   WHERE sensor_id = ?
                                   """, (sensor[0],))
                    days_with_data = [row[0] for row in cursor.fetchall()]

                    resultat[sensor[0]] = {
                        "calendar_range": (min_ts, max_ts),
                        "active_hours": total_hores,
                        "active_calendar": set(days_with_data),
                        "vbound_start": None,
                        "vbound_end": None
                    }
                else:
                    resultat[sensor[0]] = {
                        "calendar_range": None,
                        "active_hours": 0,
                        "active_calendar": set(),
                        "vbound_start": None,
                        "vbound_end": None
                    }

            return resultat

    def get_latest_data_from_sensor(self, sensor_id):
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


    def get_devices_info(self):
        """
        Obté tots els dispositius, juntament amb les seves entitats i atributs d'aquestes a partir d'un template.
        """
        url = f"{self.base_url}template"
        template = """
            {% set devices = states | map(attribute='entity_id') | map('device_id') | unique | reject('eq', None) | list %}
            {% set ns = namespace(devices = []) %}

            {% for device in devices %}
                {% set name = device_attr(device, 'name') %}
                {% set ents = device_entities(device) %}

                {% set info = namespace(entities = []) %}
                {% for entity in ents %}
                    {% set entity_name = entity %}
                    {% set entity_state = states[entity] %}
                    {% set attrs = entity_state.attributes if entity_state else {} %}

                    {% set info.entities = info.entities + [ {
                      "entity_name": entity_name,
                      "entity_state": entity_state.state if entity_state else None,
                      "entity_attrs": attrs,
                    } ] %}
                {%endfor %}

                {% set ns.devices = ns.devices + [ {
                "device_id": device,
                "device_name": name,
                "entities": info.entities
                } ] %}
            {% endfor %}

            {{ ns.devices | tojson}}
            """

        response = requests.post(url, headers=self.headers, json = {"template": template})

        if response.status_code == 200:
            # json_response = response.json()
            full_devices = response.text
            return full_devices
        else:
            logger.error(f"❌ Error en la resposta: {response.status_code}")
            logger.debug(f"📄 Cos resposta:\n     {response.text}")
            return -1























