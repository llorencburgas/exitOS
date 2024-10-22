# -*- coding: utf-8 -*-
import sqlite3
import time
import os.path
import pandas as pd
from requests import get
import traceback

class sqlDB():
    
    def __init__(self):
        "Crea la connexió a la base de dades"
        # Nom de la base de dades
        self.filename = "/share/exitos/dades.db"
        
        self.supervisor_token = os.environ.get('SUPERVISOR_TOKEN')
        self.base_url = "http://supervisor/core/api"
        
                
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
        cur.execute("CREATE TABLE dadeslab(sensor_id TEXT, timestamp NUMERIC, value)")       
        cur.execute("CREATE TABLE sensors(sensor_id TEXT, user_id TEXT, units TEXT, description TEXT, update_sensor BINARY)")
        cur.execute("CREATE TABLE homeclients(user_id TEXT, comunitat_id TEXT, token TEXT, ip TEXT, UNIQUE(user_id))")
        
        #usuari del lab el creem manualment
        cur.execute("INSERT INTO homeclients(user_id, comunitat_id, token , ip ) VALUES(?,?,?,?)", 
                    ("lab","comunitat_exit","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIzOGE2N2RkMGE0N2M0OWJjYjU2ZThkOTg2ZTY2MTE5MSIsImlhdCI6MTcyNjgyMDUzMCwiZXhwIjoyMDQyMTgwNTMwfQ.vvvdOtKH1U-3kAjaVtMXu7mR-aDb0q-YfA6c_Zx2874",
                     '192.168.191.19'))
        con.commit()
        con.close()
        
    def update(self):
        try:
            print("Iniciant Update de la BDD")
            #recuperem la llista de clients
            #con = sqlite3.connect(self.filename,10)
            cur = self.__con__.cursor()
            llista=cur.execute('SELECT * FROM homeclients').fetchall()
            cur.close()

            #per cada client....
            for i in llista:
                id_client = i[0]
                #comunitat = i[1]
                #token = i[2]
                #url = "http://"+ i[3]+":8123/api/"
                
                headers = {
                    "Authorization": "Bearer "+ self.supervisor_token,
                    "content-type": "application/json",
                    }
                
            #la llista de sensors que te el client
            sensors_list = pd.json_normalize(get(self.base_url+'states', headers=headers).json())
            
            for j in sensors_list.index:                
                #Mirem si el tenim a la bdd de sensors
                id_sensor = sensors_list.iloc[j]['entity_id']
                cur = self.__con__.cursor()
                var = (id_sensor,id_client)
                llista=cur.execute('SELECT * FROM sensors WHERE sensor_id = ? AND user_id = ?',var).fetchall()
                cur.close()
                
                if len(llista) == 0:
                    #no hem trobat el sensor de l'usuari. L'afegim.
                    cur = self.__con__.cursor()
                    values = (id_sensor,id_client,sensors_list.iloc[j]['attributes.unit_of_measurement'],'',True) #sensor_id INTEGER, user_id TEXT, units TEXT, description TEXT
                    cur.execute("INSERT INTO sensors(sensor_id, user_id, units, description, update_sensor) VALUES(?, ?, ?, ?, ?)", values)
                    cur.close()
                    self.__con__.commit()
                    print( '[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + '-- Afegit sensor: ' + id_sensor + ' - Client - ' + id_client )
                
                    #actualitzem dades del sensor
                    llista = None
                else:
                    #comprobem si cal actualitzar.
                    
                    #recuperem ultim timestamp i valor
                    cur = self.__con__.cursor()
                    var = (id_sensor,)
                    aux =cur.execute('SELECT timestamp, value FROM dades'+ id_client +' WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1',var).fetchone()
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
                var = (id_sensor,id_client)
                llista=cur.execute('SELECT update_sensor FROM sensors WHERE sensor_id = ? AND user_id = ?',var).fetchall()
                cur.close()
                
                if llista[0][0]:
                    #update esta a true.
                    print( '[' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ']' + '-- Actualitzant sensor: ' + id_sensor + ' - Client - ' + id_client )
                
                    t_fi="2099-01-01T00:00:00"
                    
                    #url = "http://"+ i[3]+":8123/api/history/period/"+t_ini+"?end_time="+t_fi+"&filter_entity_id=" + id_sensor
                    url = self.base_url + "history/period/"+t_ini+"?end_time="+t_fi+"&filter_entity_id=" + id_sensor
                    
                    aux=pd.json_normalize(get(url, headers=headers).json())
                    
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
                            cur.execute("INSERT INTO dades"+ id_client +"(sensor_id, timestamp, value) VALUES(?, ?, ?)", values)
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