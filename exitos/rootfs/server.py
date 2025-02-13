# server.py és el fitxer principal de l'aplicació web. Aquest fitxer conté la lògica de l'aplicació web i les rutes per a les diferents pàgines HTML.
import os # Importa el mòdul os
import sqlDB as db  # Importa la base de dades
from bottle import Bottle, template, run, static_file, HTTPError, redirect, request # Bottle és el que ens fa de servidor web
import optimalScheduler.OptimalScheduler as OptimalScheduler
import optimalScheduler.ForecastersManager as ForecastersManager
import optimalScheduler.forecaster as forecast
import pandas as pd
import json

# Paràmetres de l'execució
HOSTNAME = '0.0.0.0'
PORT = 8000

# Inicialització de l'aplicació i la base de dades
app = Bottle() 
database = db.sqlDB()
database.update()
optimalScheduler = OptimalScheduler.OptimalScheduler()
#model = forecastingModel()
forecast = forecast.Forecaster(debug=True)

# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./images/')

# Ruta inicial
@app.get('/')
def get_init():
    sensors = database.get_sensor_names_W()
    ip = request.environ.get('REMOTE_ADDR')
    token = database.supervisor_token
    return template('./www/main.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    ip = ip,
                    token = token)

# Ruta per la configuració de sensors
@app.get('/forecast')
def get_forecast():
    sensors = database.get_sensor_names_W()
    return template('./www/forecast.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    units = sensors['attributes.unit_of_measurement'].tolist())

# Ruta per la configuració de sensors
@app.get('/optimize')
def get_optimize():
    sensors = database.get_sensor_names_W()
    return template('./www/optimize.html', 
                    sensors = sensors['entity_id'].tolist(), 
                    units = sensors['attributes.unit_of_measurement'].tolist())    

# Ruta per enviar el formulari de optimization
@app.route('/submit-forecast', method='POST')
def submit_forecast():
    
    # Captura totes les dades del formulari com a diccionari
    form_data = request.forms.dict
    action = form_data.get('action')
    
    # Assigna les dades del formulari a variables individuals
    building_consumption_id = form_data.get('buildingConsumptionId')
    building_generation_id = form_data.get('buildingGenerationId')
    
    # Get sensors from the database
    building_consumption_df = database.get_data_from_db(building_consumption_id)
    building_generation_df = database.get_data_from_db(building_generation_id)

    if action == ['train']: #first we need to train the model
        model_consumption = forecast.train_model(building_consumption_df, y='value')
        forecast.save_model("/optimalScheduler/forecasterModels/consumptionModel.joblib") #Guara el model de consum

        model_generation = forecast.train_model(building_generation_df, y='value')
        forecast.save_model("/optimalScheduler/forecasterModels/generationModel.joblib")
        
        #forecast.create_model(building_consumption_df, y='value')
        #forecast.create_model(building_generation_df, y='value')

        return {'status': 'success', 'message': 'Model trained successfully!'}

    elif action == ['forecast']: #then we do the forecast
        # obtenir el model de consumption de la base de dades
        forecast.load_model("/optimalScheduler/forecasterModels/consumptionModel.joblib")
        forecast.load_model("/optimalScheduler/forecasterModels/generationModel.joblib")

        consumption = ForecastersManager.predictConsumption(forecast.db['model'], optimalScheduler.meteo_data, building_consumption_df) #building consumption
        production = ForecastersManager.predictProduction(forecast.db['model'], optimalScheduler.meteo_data, building_generation_df) #building prodiction
        
        # Serialitzem les dades a JSON
        plot_data = json.dumps({'consumption': consumption, 'production': production})
        
        return template('./www/plot.html', plot_data=plot_data)
        
    # Redirigeix a la plantilla 'forecast.html' i passa les dades obtingudes
    return template('./www/error.html',) #data = data


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
