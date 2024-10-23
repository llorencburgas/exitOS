# server.py és el fitxer principal de l'aplicació web. Aquest fitxer conté la lògica de l'aplicació web i les rutes per a les diferents pàgines HTML.

import os # Importa el mòdul os
import sqlDB as db  # Importa la base de dades
from bottle import Bottle, template, run, static_file, HTTPError, redirect, request # Bottle és el que ens fa de servidor web
import configparser

# Paràmetres de l'execució
HOSTNAME = '0.0.0.0'
PORT = 8000

# Inicialització de l'aplicació i la base de dades
app = Bottle() 
database = db.sqlDB()

# Get sensors filter only in KW
@app.route('/getsensors', methods=['GET'])
def get_sensors():
    try:
        sensor_names = database.getsensor_names()
        # Only the sensors in KW
        kw_sensors = [sensor for sensor in sensor_names if 'KW' in sensor.lower()]
        return jsonify(kw_sensors), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./images/')

# Ruta inicial
@app.get('/')
def get_init():
    return template('./www/main.html')
    #return database.getsensor_names()

@app.route('/submit', method='POST')
def submit():
    asset_id = request.forms.get('assetId')
    generator_id = request.forms.get('generatorId')
    source_id = request.forms.get('sourceId')
    building_consumption_id = request.forms.get('buildingConsumptionId')
    building_generation_id = request.forms.get('buildingGenerationId')
    
    # Crea una instància de ConfigParser
    config = configparser.ConfigParser()
    
    # Afegeix les dades al fitxer de configuració
    config['UserInfo'] = {
        'AssetID': asset_id,
        'GeneratorID': generator_id,
        'SourceID': source_id,
        'BuildingConsumptionID': building_consumption_id,
        'BuildingGenerationID': building_generation_id
    }
    
    # Escriu les dades al fitxer de configuració
    with open('./share/exitos/user_info.conf', 'w') as configfile:
        config.write(configfile)
    
    # Redirigeix a la plantilla principal
    return template('./www/main.html')

# Ruta dinàmica per a les pàgines HTML
@app.get('/<page>')
def get_page(page):
    # Ruta del fitxer HTML
    file_path = f'./www/{page}.html'
    # Comprova si el fitxer existeix
    if os.path.exists(file_path):
        # Control de dades segons la pàgina
         return static_file(f'{page}.html', root='./www/')
    else:
        return HTTPError(404, "Page not found")
    

#################################################################################
#   Hem acabat de definir totes les url i que cal fer per cada una d'elles.     #
#   Executem el servidor                                                        #
#################################################################################

# Funció main que encén el servidor web.
def main():
    run(app=app, host=HOSTNAME, port=PORT)

# Executem la funció main
if __name__ == "__main__":
    main()
