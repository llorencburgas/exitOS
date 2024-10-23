# -*- coding: utf-8 -*-
import sqlite3
import time
import pandas as pd
from requests import get
import traceback
import os

class sqlDB():
    def __init__(self):
        "Crea la connexió a la base de dades"
        # Nom de la base de dades
        self.filename = "/share/exitos/dades.db"
        
        #per conectar a la api de home assistant
        self.supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        self.base_url = "http://supervisor/core/api/"
        self.headers = {
                    "Authorization": "Bearer" + self.supervisor_token,
                    "content-type": "application/json",
                    }

        # Comprova si la base de dades existeix
        if not os.path.isfile(self.filename):
            print("No s'ha trobat la BDD. La creem de nou!")
            "No existeix, creem la base de dades de nou"
            self.__install__()  # Assegura't que aquest mètode està definit i funciona correctament
            
        # Connexió a la base de dades
        self.__con__ = sqlite3.connect(self.filename, timeout=10)
    
    def __del__(self):
        "Destructor de l'objecte. Tanca la connexió de manera segura"
        try:
            self.__con__.close()  # Tanca la connexió, si existeix
        except AttributeError:
            pass  # Si la connexió no existeix, no fem res
    
    def __install__(self):
        "Crea les taules inicials de la BDD de nou"
           
        print("Creem una BDD nova")
        con = sqlite3.connect(self.filename)        
        cur = con.cursor()
        
        #creem les taules
        cur.execute("CREATE TABLE dades(sensor_id TEXT, timestamp NUMERIC, value)")       
        cur.execute("CREATE TABLE sensors(sensor_id TEXT, units TEXT, description TEXT, update_sensor BINARY)")
        
        con.commit()
        con.close()
        
    def getsensor_names_Wh(self):
        print("Demanda llista de noms de sensors!")

        response = get(self.base_url + 'states', headers=self.headers)
        sensors_list = pd.json_normalize(response.json())

        # Comprova que la columna 'entity_id' existeix
        if 'entity_id' in sensors_list.columns:
            aux = sensors_list[['entity_id', 'attributes.unit_of_measurement']]
            llista = aux[aux['attributes.unit_of_measurement'] == 'Wh']
            print(llista)
            llista = pd.concat([llista, aux[aux['attributes.unit_of_measurement'] == 'kWh']])
            print(llista)
            return llista
        else:
            print("'entity_id' column not found in response data")
            print(f"Available columns: {sensors_list.columns.tolist()}")
            return 'No funciona'  # Torna un DataFrame buit si no es troba

        
        
    
    def update(self):
        try:
            print("Iniciant Update de la BDD")
                
            #la llista de sensors que te el client
            sensors_list = pd.json_normalize(get(self.base_url+'states', headers=self.headers).json())
            
            for j in sensors_list.index:                
                #Mirem si el tenim a la bdd de sensors
                id_sensor = sensors_list.iloc[j]['entity_id']
                cur = self.__con__.cursor()
                var = (id_sensor)
                llista=cur.execute('SELECT * FROM sensors WHERE sensor_id = ?',var).fetchall()
                cur.close()
                
                if len(llista) == 0:
                    #no hem trobat el sensor de l'usuari. L'afegim.
                    cur = self.__con__.cursor()
                    values = (id_sensor,sensors_list.iloc[j]['attributes.unit_of_measurement'],'',True) #sensor_id INTEGER, user_id TEXT, units TEXT, description TEXT
                    cur.execute("INSERT INTO sensors(sensor_id, units, description, update_sensor) VALUES(?, ?, ?, ?)", values)
                    cur.close()
                    self.__con__.commit()
                    print( '[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + '-- Afegit sensor: ' + id_sensor )
                
                    #actualitzem dades del sensor
                    llista = None
                else:
                    #comprobem si cal actualitzar.
                    
                    #recuperem ultim timestamp i valor
                    cur = self.__con__.cursor()
                    var = (id_sensor,)
                    aux =cur.execute('SELECT timestamp, value FROM dades WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1',var).fetchone()
                    if aux == None:
                        llista = None
                    else:
                        llista, valor_ant = aux
                    cur.close()
                
                if llista is None:
                    t_ini="2022-01-01T00:00:00"
                    valor_ant= []
                else:
                    t_ini= llista
                 
                #Comprobem si aquest sensor s'ha d'actualitzar
                id_sensor = sensors_list.iloc[j]['entity_id']
                cur = self.__con__.cursor()
                var = (id_sensor)
                llista=cur.execute('SELECT update_sensor FROM sensors WHERE sensor_id = ? ',var).fetchall()
                cur.close()
                
                if llista[0][0]:
                    #update esta a true.
                    print( '[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + '-- Actualitzant sensor: ' + id_sensor  )
                
                    t_fi="2099-01-01T00:00:00"
                    
                    url = self.base_url + "history/period/"+t_ini+"?end_time="+t_fi+"&filter_entity_id=" + id_sensor
                    
                    aux=pd.json_normalize(get(url, headers=self.headers).json())
                    
                    #per cada valor que he obtingut del sensor
                    cur = self.__con__.cursor()
                    for column in aux.columns:
                        valor = aux[column][0]['state']
                        #comprovem si el valor anterior es igual a l'anterior -> no l'afegim o be unknown, buit, unavailable -> nan
                        if (valor == 'unknown') | (valor == 'unavailable') | (valor == ''):
                            valor = 'nan'
                        if valor_ant != valor:
                            valor_ant = valor# canviem el valor anterior a l'actual
                            TS = aux[column][0]['last_updated']
                            values = (id_sensor,TS, valor)
                            cur.execute("INSERT INTO dades (sensor_id, timestamp, value) VALUES(?, ?, ?)", values)
                    cur.close()
                    self.__con__.commit()
        except:
            print('['+time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())+']'+"-- No s'ha pogut inserir o descarregar dades!")
            traceback.print_exc() 


    def query(self, sql):
        "Executa una query a la bdd"
        cur = self.__con__.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        cur.close()
        return result