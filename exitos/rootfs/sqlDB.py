import os
import logging
import sqlite3
import numpy as np
import pandas as pd
from requests import get
from datetime import datetime, timedelta, timezone

from exitos.rootfs.bottle import response


class sqlDB():
    def __init__(self):
        """
        Constructor de la classe. \n
        Crea la connexió a la base de dades
        """

        print("INICIANT LA BASE DE DATES...")

        # DADES A DESCOMENTAR QUAN SIGUI REMOT ****
        self.database_file = "/share/exitos/dades.db"
        self.config_path = "/share/exitos/user_info.conf"
        self.supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        self.base_url = "http://supervisor/core/api/"

        #Dades a comentar quan sigui remot
        # self.database_file = "dades.db"
        # self.config_path = "user_info.config"
        # self.supervisor_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI5YzMxMjU1MzQ0NGY0YTg5YjU5NzQ5NWM0ODI2ZmNhZiIsImlhdCI6MTc0MTE3NzM4NSwiZXhwIjoyMDU2NTM3Mzg1fQ.5-ST2_WQNJ4XRwlgHK0fX8P6DnEoCyEKEoeuJwl-dkE"
        # self.base_url = "http://margarita.udg.edu:28932/api/"
        # ****************************************
        self.headers = {
            "Authorization": "Bearer " + self.supervisor_token,
            "Content-Type": "application/json"
        }

        #comprovem si la Base de Dades existeix
        if not os.path.isfile(self.database_file):
            print("La base de dades no existeix")
            print("Creant la base de dades...")
            self.__initDB__()

        #connecta a la Base de Dades
        self.__conn__ = sqlite3.connect(self.database_file, timeout=10)

    def __del__(self):
        """
        Destructor de l'objecte. Tanca la connexió de manera segura
        """
        try:
            self.__conn__.close()
        except AttributeError:
            pass

    def __initDB__(self):
        """
        Crea les taules de la base de dades \n
            -> DADES: conté els valors i timestamps de les dades \n
            -> SENSORS: conté la info dels sensors
        """

        print("S'ESTÀ CREANT LA BASE DE DATES...")

        con = sqlite3.connect(self.database_file)
        cur = con.cursor()

        #creant les taules
        cur.execute("CREATE TABLE dades(sensor_id TEXT, timestamp NUMERIC, value)")
        cur.execute("CREATE TABLE sensors(sensor_id TEXT, units TEXT, update_sensor BINARY, save_sensor BINARY)")

        con.commit()
        con.close()

    def query_select(self, sensor_id, value, db):
        """
        Executa una query SQL a la base de dades
        :param sensor_id: id del sensor a mirar
        :param value: valor de la base de dades que es vol obtenir
        :param db: Base de dades a utilitzar
        :return: valor obtingut de la Base de Dades al executar la query
        """
        cur = self.__conn__.cursor()
        cur.execute("SELECT " + value + " FROM " + db + " WHERE sensor_id = '" + sensor_id + "'" )
        result = cur.fetchall()
        cur.close()

        return result

    def get_all_sensors(self):
        """
        Obté una llista amb tots els id i "friendly name" dels sensors de la base de dades
        """
        response = get(self.base_url + "states", headers=self.headers)
        sensors_list = pd.json_normalize(response.json())

        if 'entity_id' in sensors_list.columns:
            sensors = sensors_list[['entity_id', 'attributes.friendly_name']]
            return sensors
        else:
            return None

    def get_sensors_save(self, sensors):
        """
        Obté una llista amb l'estat save_sensor dels sensors de la base de dades en el mateix ordre que sensors
        :param sensors: llista amb id dels sensors a obtenir l'estat save_sensor'
        """
        sensors_save = []
        for sensor in sensors:
            aux = self.query_select(sensor, "save_sensor", "sensors")

            if aux: #assegurem que aux tingui contingut
                sensors_save.append(aux[0][0])
            else:
                sensors_save.append(0)

        return sensors_save

    def update_sensor_active(self, sensor, active):
        """
        Actualitza a la base de dades l'estat save_sensor pel sensor indicat
        :param sensor: sensor a modificar
        :param active: estat nou del sensor
        """
        cur = self.__conn__.cursor()
        cur.execute("UPDATE sensors SET save_sensor = ? WHERE sensor_id = ?", (active, sensor))
        cur.close()
        self.__conn__.commit()

    def update(self):
        """
        Actualitza la base de dades amb la API del Home Assistant.
        Aquesta funció sincronitza els sensors existents amb la base de dades i
        actualitza els valors històrics únicament si estan marcats com a
        "update_sensor" i "save_sensor" TRUE
        """
        logging.info("Iniciant l'actualització de la base de dades...")

        #obtenim la llista de sensors de la API
        sensors_list = pd.json_normalize(
            get(self.base_url + "states", headers=self.headers).json()
        )

        for j in sensors_list.index: #per a cada sensor de la llista
            sensor_id = sensors_list.iloc[j]["entity_id"]

            #obtenim de la nostra BD el sensor amb id igual al obtingut anteriorment

            sensor_info = self.query_select(sensor_id, "*", "sensors")

            #si no hem obtingut cap sensor ( és a dir, no existeix a la nosta BD)
            if len(sensor_info) == 0:
                cur = self.__conn__.cursor()
                values_to_insert = (sensor_id,
                                    sensors_list.iloc[j]["attributes.unit_of_measurement"],
                                    True,
                                    True)
                cur.execute("INSERT INTO sensors (sensor_id, units, update_sensor, save_sensor) VALUES (?,?,?,?)", values_to_insert)
                cur.close()
                self.__conn__.commit()
                print("[" + datetime.now(timezone.utc).strftime("%d-%b-%Y   %X")
                             + "] Afegit un nou sensor a la base de dades: " + sensor_id)

                sensor_info = None
                last_date_saved = None

            save_sensor = self.query_select(sensor_id,"save_sensor", "sensors")[0][0]
            update_sensor = self.query_select(sensor_id,"update_sensor", "sensors")[0][0]
            if save_sensor and update_sensor:
                print("[" + datetime.now(timezone.utc).strftime("%d-%b-%Y   %X") + "] Actualitzant sensor: " + sensor_id)

                last_date_saved = self.query_select(sensor_id,"timestamp, value", "dades")
                if len(last_date_saved) == 0:
                    start_time = datetime.now(timezone.utc) - timedelta(days=21)
                    last_value = []
                else:
                    last_date_saved, last_value = last_date_saved[0]
                    start_time = datetime.fromisoformat(last_date_saved)

                current_date = datetime.now(timezone.utc)

                while start_time < current_date:
                    end_time = start_time + timedelta(days = 7)

                    string_start_date = start_time.strftime('%Y-%m-%dT%H:%M:%S')
                    string_end_date = end_time.strftime('%Y-%m-%dT%H:%M:%S')

                    url = (
                        self.base_url + "history/period/" + string_start_date +
                        "?end_time=" + string_end_date +
                        "&filter_entity_id=" + sensor_id
                    )

                    sensor_data_historic = pd.DataFrame()

                    repsonse = get(url, headers=self.headers)
                    if response.status_code == 200:
                        try:
                            sensor_data_historic = pd.json_normalize(repsonse.json())
                        except ValueError as e:
                            print("Error parsing JSON: " + str(e))
                    elif response.status_code == 500:
                        print("Server error (500): Internal server error at sensor ", sensor_id)
                        sensor_data_historic = pd.DataFrame()
                    else:
                        print("Request failed with status code: ", response.status_code)
                        sensor_data_historic = pd.DataFrame()

                    #actualitzem el valor obtingut de l'històric del sensor
                    cur = self.__conn__.cursor()
                    for column in sensor_data_historic.columns:
                        value = sensor_data_historic[column][0]['state']

                        #mirem si el valor és vàlid
                        if value == 'unknown' or value == 'unavailable' or value == '':
                            value = np.nan
                        if last_value != value:
                            last_value = value
                            time_stamp = sensor_data_historic[column][0]['last_changed']
                            cur.execute("INSERT INTO dades (sensor_id, timestamp, value) VALUES (?,?,?)",
                                        (sensor_id, time_stamp, value))

                    cur.close()
                    self.__conn__.commit()

                    start_time += timedelta(days = 7)

        print("[" + datetime.now(timezone.utc).strftime("%d-%b-%Y   %X") +
                     "] TOTS ELS SENSORS HAN ESTAT ACTUALITZATS")




















