
import os
import sqlDB as db
import json
from bottle import Bottle, template, run, static_file, HTTPError, redirect, request, response

# PARÀMETRES DE L'EXECUCIÓ
HOSTNAME = '0.0.0.0'
PORT = 8000

#INICIACIÓ DE L'APLICACIÓ I LA BASE DE DADES
app = Bottle()
database = db.sqlDB()

# COMENTAT PER AGILITZAR EL DEBUG, RECORDA A DESCOMENTAR-HO DESPRÉS!!!!
# database.update()

#Ruta inicial
# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./images/')

# Ruta inicial
@app.get('/')
def get_init():
    ip = request.environ.get('REMOTE_ADDR')
    token = database.supervisor_token
    return template('./www/main.html',
                    ip = ip,
                    token = token)

#Ruta per a configurar quins sensors volem guardar
@app.get('/sensors')
def get_sensors():
    sensors = database.get_all_sensors()
    sensors_id = sensors['entity_id'].tolist()
    sensors_name = sensors['attributes.friendly_name'].tolist()
    sensors_save = database.get_sensors_save(sensors_id)


    context = {
        "sensors_id": sensors_id,
        "sensors_name": sensors_name,
        "sensors_save": sensors_save
    }

    return template('./www/sensors.html', sensors = context )

# @app.get('/update_sensors')
# def update_sensors():
#     data = request.json
#     print("Received JSON:", json.dumps(data, indent=2))
#     sensors = data.get("sensors", [])
#
#     if not sensors:
#         response.status = 400
#         return {"error": "No data received"}
#
#     #Actualitzar la base de dades per a cada sensor
#     for sensor in sensors:
#         sensor_id = sensor.get("sensor_id")
#         is_active = sensor.get("active")
#         database.update_sensor_active(sensor_id, is_active)
#
#     return{"success": True, "updated_sensors": len(sensors)}

@app.post('/update_sensors')
def update_sensors():
    checked_sensors = request.forms.getall("sensor_id")
    sensors = database.get_all_sensors()
    sensors_id = sensors['entity_id'].tolist()

    for sensor_id in sensors_id:
        is_active = sensor_id in checked_sensors
        database.update_sensor_active(sensor_id, is_active)

    print(f"Sensors actualitzats: {checked_sensors}")
    return redirect("/sensors")

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