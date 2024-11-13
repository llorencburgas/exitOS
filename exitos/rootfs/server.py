# server.py és el fitxer principal de l'aplicació web. Aquest fitxer conté la lògica de l'aplicació web i les rutes per a les diferents pàgines HTML.
import os # Importa el mòdul os
import sqlDB as db  # Importa la base de dades
from bottle import Bottle, template, run, static_file, HTTPError, redirect, request # Bottle és el que ens fa de servidor web
import configparser
from forecastingModel import forecastingModel  # Importa la classe correcta

# Paràmetres de l'execució
HOSTNAME = '0.0.0.0'
PORT = 8000

# Inicialització de l'aplicació i la base de dades
app = Bottle() 
database = db.sqlDB()
model = forecastingModel()

# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./images/')

# Ruta inicial
@app.get('/')
def get_init():
    sensors = database.get_sensor_names_Wh()
    ip = request.environ.get('REMOTE_ADDR')
    token = database.supervisor_token
    return template('./www/main.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    ip = ip,
                    token = token)

# Ruta per la configuració de sensors
@app.get('/configuration')
def get_configuration():
    sensors = database.get_sensor_names_Wh()
    return template('./www/configuration.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    units = sensors['attributes.unit_of_measurement'].tolist())    

# Ruta per enviar el formulari de configuració
@app.route('/submit', method='POST')
def submit():
     # Captura totes les dades com a diccionari
    form_data = request.forms.dict
    print("Form Data:", form_data)  # Mostra les dades per depurar
    
    # Assigna les dades directament o amb `get` si cal
    asset_id = form_data.get('assetID')
    generator_id = form_data.get('generatorId')
    source_id = form_data.get('sourceId')
    building_consumption_id = form_data.get('buildingConsumptionId')
    building_generation_id = form_data.get('buildingGenerationId')
    
    # La resta del codi segueix igual
    config = configparser.ConfigParser()
    config['UserInfo'] = {
        'AssetID': str(asset_id),
        'GeneratorID': str(generator_id),
        'SourceID': str(source_id),
        'BuildingConsumptionID': str(building_consumption_id),
        'BuildingGenerationID': str(building_generation_id),
    }

    config_path = './share/exitos/user_info.conf'

    # Escriu les dades al fitxer de configuració
    with open(config_path, 'w') as configfile:
        config.write(configfile)

    # Actualitza la configuració carregada
    data = database.load_user_info_config()  # Crida a la funció per obtenir les dades
    sensor_data = data[0]  # Obté les dades dels sensors

    # Formata les dades per passar-les al template
    formatted_data = {sensor_id: df.to_dict(orient='records') for sensor_id, df in sensor_data.items()}

    # Redirigeix a la plantilla forecast.html passant les dades
    return template('./www/forecast.html', sensor_data=formatted_data)

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
#   Hem acabat de definir totes les url i què cal fer per cada una d'elles.     #
#   Executem el servidor                                                        #
#################################################################################

# Funció main que encén el servidor web.
def main():
    run(app=app, host=HOSTNAME, port=PORT)

# Executem la funció main
if __name__ == "__main__":
    main()
