import os
import sqlite3

import numpy as np
import pandas as pd
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
        logger.info("INICIANT LA BASE DE DADES...")

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
            cur.execute("CREATE TABLE IF NOT EXISTS sensors(sensor_id TEXT, units TEXT, update_sensor BINARY, save_sensor BINARY)")
            cur.execute("CREATE TABLE IF NOT EXISTS forecasts(forecast_name TEXT, forecast_run_time NUMERIC, forecasted_time NUMERIC, predicted_value REAL, real_value REAL)")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_dades_sensor_id_timestamp ON dades(sensor_id, timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id ON sensors(sensor_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_forecasts_forecast_name ON forecasts(forecast_name)")

            con.commit()
        logger.info("Base de dades creada correctament.")

    def _get_connection(self):
        return sqlite3.connect(self.database_file)

    def query_select(self, table:str, column:str, sensor_id: str, con) -> List[Any]:
        """
        Executa una query SQL a la base de dades
        """
        cur = con.cursor()
        cur.execute(f"SELECT {column} FROM {table} WHERE sensor_id = ?", (sensor_id,))
        result = cur.fetchone()
        cur.close()
        return result


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

    # def update_database(self, sensor_to_update):
    #     logger.info("INICIANT L'ACTUALITZACIÓ DE LA BASE DE DADES...")
    #
    #     con = self.__open_connection__()
    #
    #     # obtenim la llista de sensors de la API
    #     if sensor_to_update == "all":
    #         sensors_list = pd.json_normalize(
    #             get(self.base_url + "states", headers=self.headers).json()
    #         )
    #     else:
    #         sensors_list = pd.json_normalize(
    #             get(self.base_url + "states?filter_entity_id=" + sensor_to_update, headers=self.headers).json()
    #         )
    #         if len(sensors_list) == 0:
    #             logger.error("No existeix un sensor amb l'ID indicat")
    #             return None
    #
    #     local_tz = tzlocal.get_localzone()
    #     current_date = datetime.now(local_tz)
    #
    #     for j in sensors_list.index:
    #         sensor_id = sensors_list.iloc[j]['entity_id']
    #
    #         sensor_info = self.query_select(sensor_id, "*", "sensors", con)
    #
    #         if len(sensor_info) == 0:
    #             cur = con.cursor()
    #             values_to_insert = (sensor_id,
    #                                 sensors_list.iloc[j]["attributes.unit_of_measurement"],
    #                                 True,
    #                                 False)
    #             cur.execute("INSERT INTO sensors (sensor_id, units, update_sensor, save_sensor) VALUES (?,?,?,?)", values_to_insert)
    #             cur.close()
    #             con.commit()
    #             sensor_info = None
    #             last_date_saved = None
    #             logger.debug(f"[ {current_date.strftime('%d-%b-%Y   %X')} ] Afegit un nou sensor a la base de dades: {sensor_id}")
    #
    #         save_sensor = self.query_select(sensor_id, "save_sensor", "sensors", con)[0][0]
    #         update_sensor = self.query_select(sensor_id, "update_sensor", "sensors", con)[0][0]
    #
    #         if save_sensor and update_sensor:
    #             logger.debug(f"[ {current_date.strftime('%d-%b-%Y   %X')} ] Actualitzant sensor: {sensor_id}")
    #
    #             last_date_saved = self.query_select(sensor_id, "timestamp, value", "dades", con)
    #             if len(last_date_saved) == 0:
    #                 start_time = current_date - timedelta(days=21)
    #                 last_value = []
    #             else:
    #                 last_date_saved, last_value = last_date_saved[0]
    #                 start_time = datetime.fromisoformat(last_date_saved)
    #
    #             while start_time <= current_date:
    #                 end_time = start_time + timedelta(days=7)
    #
    #                 string_start_date = start_time.strftime('%Y-%m-%dT%H:%M:%S')
    #                 string_end_date = end_time.strftime('%Y-%m-%dT%H:%M:%S')
    #
    #                 url = (
    #                     self.base_url + "history/period/" + string_start_date +
    #                     "?end_time=" + string_end_date +
    #                     "&filter_entity_id=" + sensor_id
    #                     + "&minimal_response&no_attributes"
    #                 )
    #
    #                 sensor_data_historic = pd.DataFrame()
    #
    #                 response = get(url, headers=self.headers)
    #                 if response.status_code == 200:
    #                     try:
    #                         response_data = response.json()
    #                         flattened_data = [item for sublist in response_data for item in sublist]
    #                         sensor_data_historic = pd.json_normalize(flattened_data)
    #
    #                     except ValueError as e:
    #                         logger.error(f"Error parsing JSON: {str(e)}")
    #                 elif response.status_code == 500:
    #                     logger.critical(f"Server error (500): Internal server error at sensor {sensor_id}")
    #                     sensor_data_historic = pd.DataFrame()
    #                 else:
    #                     logger.error(f"Request failed with status code: {response.status_code}")
    #                     sensor_data_historic = pd.DataFrame()
    #
    #                 logger.info(response.json())
    #                 logger.debug(f"start_date {string_start_date}")
    #                 logger.debug(f"end_date {string_end_date}")
    #                 logger.debug(f"url {url}")
    #                 logger.debug(f"status_code {response.status_code}")
    #                 logger.debug(f"response {response.text}")
    #                 logger.info(f"sensor_data_historic {sensor_data_historic}")
    #
    #                 all_data = []
    #                 if len(sensor_data_historic) > 0:
    #                     logger.info("sensor_data_historic has values (?)")
    #                     for column in sensor_data_historic.columns:
    #                         data_point = sensor_data_historic[column][0]
    #                         logger.critical(f"DATA: {data_point}")
    #                         all_data.append({
    #                             'timestamp': data_point['last_changed'],
    #                             'value': data_point['state']
    #                         })
    #
    #                         #això hauria d'estar dins el FOR??
    #                     df = pd.DataFrame(all_data)
    #                     logger.critical(df.columns)
    #                     df['value'] = pd.to_numeric(df['value'], errors='coerce')
    #                     df['timestamp'] = pd.to_datetime(df['timestamp'])
    #                     df['hour'] = df['timestamp'].dt.floor('H')
    #
    #                     df_grouped = df.groupby('hour').mean(numeric_only=True).reset_index()
    #
    #                     cur = con.cursor()
    #                     for idx, row in df_grouped.iterrows():
    #                         mean_value = row['value']
    #                         time_stamp = row['hour'].isoformat()
    #
    #                         if np.isnan(mean_value):
    #                             continue  # saltem valors nuls
    #
    #                         # Només inserim si ha canviat respecte l'últim valor
    #                         if last_value != mean_value:
    #                             last_value = mean_value
    #                             cur.execute(
    #                                 "INSERT INTO dades (sensor_id, timestamp, value) VALUES (?,?,?)",
    #                                 (sensor_id, time_stamp, mean_value)
    #                             )
    #                     cur.close()
    #                     con.commit()

    def clean_database_hourly_average(self):
        logger.warning("INICIANT NETEJA DE LA BASE DE DADES")
        with self._get_connection() as con:
            sensor_ids = [row[0] for row in con.execute("SELECT DISTINCT sensor_id FROM dades").fetchall()]

            for sensor_id in sensor_ids:
                logger.info(f"Processant sensor: {sensor_id}")
                df = pd.read_sql_query(
                    f"SELECT timestamp, value FROM dades WHERE sensor_id = ?", con, params=(sensor_id,)
                )
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                df['hour'] = df['timestamp'].dt.floor('H')
                df_grouped = df.groupby('hour').mean(numeric_only=True).reset_index()

                con.execute("DELETE FROM dades WHERE sensor_id = ?", (sensor_id,))
                con.executemany(
                    "INSERT INTO dades (sensor_id, timestamp, value) VALUES (?, ?, ?)",
                    [(sensor_id, row['hour'].isoformat(), row['value']) for _,
                    row in df_grouped.iterrows() if pd.notna(row['value'])]
                )
                con.commit()
        logger.info("NETEJA COMPLETADA")
        self.vacuum()


    def old_update_database(self, sensor_to_update):
        """
        Actualitza la base de dades amb la API del Home Assistant.
        """
        logger.info("Iniciant l'actualització de la base de dades...")

        #obtenim la llista de sensors de la API
        if sensor_to_update == "all":
            sensors_list = pd.json_normalize(
                get(self.base_url + "states", headers=self.headers).json()
            )
        else:
            sensors_list = pd.json_normalize(
                get(self.base_url + "states?filter_entity_id=" + sensor_to_update, headers=self.headers).json()
            )
            if len(sensors_list) == 0:
                logger.error("No existeix un sensor amb l'ID indicat")
                return None


        local_tz = tzlocal.get_localzone()  # Gets system local timezone (e.g., 'Europe/Paris')
        current_date = datetime.now(local_tz)

        with self._get_connection() as con:
            for j in sensors_list.index:
                sensor_id = sensors_list.iloc[j]["entity_id"]

                sensor_info = self.query_select("sensors", "*", sensor_id, con)

                #si no hem obtingut cap sensor ( és a dir, no existeix a la nosta BD)
                if len(sensor_info) == 0:
                    cur = con.cursor()
                    values_to_insert = (
                        sensor_id,
                        sensors_list.iloc[j]["attributes.unit_of_measurement"],
                        True,
                        False
                    )
                    cur.execute(
                        "INSERT INTO sensors (sensor_id, units, update_sensor, save_sensor) VALUES (?,?,?,?)",
                        values_to_insert
                    )
                    cur.close()
                    con.commit()
                    logger.debug(f"[ {current_date.strftime('%d-%b-%Y   %X')} ] Afegit un nou sensor a la base de dades: {sensor_id}")

                save_sensor = self.query_select("sensors","save_sensor", sensor_id, con)[0]
                update_sensor = self.query_select("sensors","update_sensor", sensor_id, con)[0]

                if save_sensor and update_sensor:
                    logger.debug(f"[ {current_date.strftime('%d-%b-%Y   %X')} ] Actualitzant sensor: {sensor_id}")

                    last_date_saved = self.query_select("dades","timestamp, value", sensor_id, con)
                    if len(last_date_saved) == 0:
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
                                logger.error(f"Error parsing JSON: {str(e)}")
                                sensor_data_historic = pd.DataFrame()
                        elif response.status_code == 500:
                            logger.critical(f"Server error (500): Internal server error at sensor {sensor_id}")
                            sensor_data_historic = pd.DataFrame()
                        else:
                            logger.error(f"Request failed with status code: {response.status_code}")
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


            self.vacuum()
        logger.info(f"[ {current_date.strftime('%d-%b-%Y   %X')} ] TOTS ELS SENSORS HAN ESTAT ACTUALITZATS")

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
                INSERT INTO forecasts (forecast_name, forecast_run_time, forecasted_time, predicted_value, real_value) 
                VALUES (?,?,?,?,?)
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

    def remove_forecast(self, forecast_id):
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM forecasts WHERE forecast_name = ?",(forecast_id,))
            con.commit()
            cur.close()

    def vacuum(self):
        with self._get_connection() as con:
            logger.debug("VACUUMING")
            con.execute("VACUUM")
            logger.debug("VACUUM COMPLETE")






















