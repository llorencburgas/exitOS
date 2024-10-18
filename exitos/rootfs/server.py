# server.py és el fitxer principal de l'aplicació web. Aquest fitxer conté la lògica de l'aplicació web i les rutes per a les diferents pàgines HTML.

import os # Importa el mòdul os
import sqlDB as db  # Importa la base de dades
from bottle import Bottle, template, run, static_file, HTTPError, redirect # Bottle és el que ens fa de servidor web
import sqlite3 # Importa el mòdul sqlite3

# Paràmetres de l'execució
HOSTNAME = '0.0.0.0'
PORT = 8000

# Inicialització de l'aplicació i la base de dades
app = Bottle() 
database = db.sqlDB()

#Actualitzem les dades
database.update()

# Ruta per servir fitxers estàtics i imatges des de 'www'
@app.get('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./images/')

# Ruta inicial
@app.get('/')
def get_init():
    return template('./www/main.html')


@app.route('/submit', method='POST')
def submit():
    name = request.forms.get('name')
    email = request.forms.get('email')
    age = request.forms.get('age')
    country = request.forms.get('country')
    
    config = configparser.ConfigParser()
    config['UserInfo'] = {
        'Name': name,
        'Email': email,
        'Age': age,
        'Country': country
    }
    
    with open('./shared/user_info.conf', 'w') as configfile:
        config.write(configfile)
    
    return "Information saved successfully!"


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
