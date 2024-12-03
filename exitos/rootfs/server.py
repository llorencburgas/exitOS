# server.py és el fitxer principal de l'aplicació web. Aquest fitxer conté la lògica de l'aplicació web i les rutes per a les diferents pàgines HTML.
import os # Importa el mòdul os
import sqlDB as db  # Importa la base de dades
from bottle import Bottle, template, run, static_file, HTTPError, redirect, request # Bottle és el que ens fa de servidor web
import optimalScheduler.OptimalScheduler as OptimalScheduler
import optimalScheduler.ForecastersManager as ForecastersManager

# Paràmetres de l'execució
HOSTNAME = '0.0.0.0'
PORT = 8000

# Inicialització de l'aplicació i la base de dades
app = Bottle() 
database = db.sqlDB()
database.update()
#model = forecastingModel()

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
@app.get('/forecast')
def get_forecast():
    sensors = database.get_sensor_names_Wh()
    return template('./www/forecast.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    units = sensors['attributes.unit_of_measurement'].tolist())

# Ruta per la configuració de sensors
@app.get('/optimize')
def get_optimize():
    sensors = database.get_sensor_names_Wh()
    return template('./www/optimize.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    units = sensors['attributes.unit_of_measurement'].tolist())    

# Ruta per enviar el formulari de optimization
@app.route('/submit-forecast', method='POST')
def submit_forecast():
    
    # Captura totes les dades del formulari com a diccionari
    form_data = request.forms.dict
    action = form_data.get('action')
    print("Form Data:", form_data)  # Mostra les dades per depurar
    
    # Assigna les dades del formulari a variables individuals
    building_consumption_id = form_data.get('buildingConsumptionId')
    building_generation_id = form_data.get('buildingGenerationId')
    #sensors_id = [building_consumption_id, building_generation_id]
    '''les dades han de ser seleccionades de la base de dades i s'han d'extreure d'allà els valors per fer el forecast'''
    #data = database.get_filtered_data(sensors_id)
    
    if action == 'train':
        '''ara mateix el train es fa directament amb el forecast'''
        #print('Training model', data)
    elif action == 'forecast':
        #building_consumption_id = database.get_filtered_data([building_consumption_id])
        #building_generation_id = database.get_filtered_data([building_generation_id])
        consumption = ForecastersManager.predictConsumption(OptimalScheduler.meteo_data, building_consumption_id) #building consumption
        production = ForecastersManager.predictProduction(OptimalScheduler.meteo_data, building_generation_id) #building prodiction
        # mostrem les dades en un gràfic
        plot_data = {'consumption': consumption, 'production': production}
        return template('./www/plot.html', plot_data = plot_data)

    
    # Redirigeix a la plantilla 'forecast.html' i passa les dades obtingudes
    return template('./www/forecast.html',) #data = data


# Ruta per enviar el formulari de forecast
@app.route('/submit-optmize', method='POST')
def submit_optimize():
    
    # Captura totes les dades del formulari com a diccionari
    form_data = request.forms.dict
    print("Form Data:", form_data)  # Mostra les dades per depurar
    
    # Assigna les dades del formulari a variables individuals
    asset_id = form_data.get('assetID')
    generator_id = form_data.get('generatorId')
    source_id = form_data.get('sourceId')
    building_consumption_id = form_data.get('buildingConsumptionId')
    building_generation_id = form_data.get('buildingGenerationId')
    sensors_id = [asset_id, generator_id, source_id, building_consumption_id, building_generation_id]
    data = database.get_filtered_data(sensors_id)

    # Cridem la funció de optimalScheduler
    OptimalScheduler.startOptimizationNoPipe()
    '''la idea és mostrar les dades en un gràfic'''
    
    # Redirigeix a la plantilla 'forecast.html' i passa les dades obtingudes
    return template('./www/forecast.html', data = data) #data = data

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
