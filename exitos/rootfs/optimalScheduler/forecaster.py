# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

import joblib
import holidays
import warnings
warnings.filterwarnings('ignore')
import sys
import logging

class Forecaster:
        def __init__(self, debug = False):
            """
            Constructor per defecte
            """
            
            self.debug = debug  # per mostrar per consola prints!
            self.search_space_conf_file = '../search_space.conf'
            self.db = dict()  # El model que hem creat.
        
        def windowing_grup(self, datasetin, look_back_ini=24, look_back_fi=48):
            """
            Funcio per crear les variables del windowing. Treballa sobre un dataset i inclou la variable objectiu!
            les variables creades es diran com l'original (legacy) i s'afegira '_' i el numero de desplacament al final del nom.
            Es tindran en compte les hores en el rang [ini, fi)
            
            Parametres:
                datasetin - pandas dataframe amb datetime com a index
                
                look_back_ini - on comença la finestra numero d'observacions (24 -> el dia anterior si es horari)
                
                look_back_fi - fins on arriba numero d'observacions (48-< el dia anterior si es orari)
                

            Retorna:
                dataset - el datasetin + les variables desplaçades en columnes noves
            """
            
            dataset = datasetin.copy()
            for i in range(0, len(dataset.columns)):
                for j in range(look_back_ini, look_back_fi):
                    dataset[dataset.columns[i]+'_'+str(j)] = dataset[dataset.columns[i]].shift(j)
            
            return dataset
        
        def windowing_univariant(self, datasetin, look_back_ini=0, look_back_fi=24, variable=''):
            """
            Funcio per crear les variables del windowing. de la variable indicada Treballa sobre un dataset i inclou la variable objectiu!
            les variables creades es diran com l'original (legacy) i s'afegira '_' i el numero de desplacament al final del nom.
            Es tindran en compte les hores en el rang [ini, fi).
            
            Parametres:
                datasetin - pandas dataframe amb datetime com a index
                
                look_back_ini - on comença la finestra numero d'observacions (25 -> el dia anterior si es horari)
                
                look_back_fi - fins on arriba numero d'observacions (48-< el dia anterior si es horari)

                vari - la variable on apliquem el windowing
                
            Retorna:
                dataset - el datasetin + les variables desplaçades en columnes noves
            """
            dataset = datasetin.copy()
            for i in range(0, len(dataset.columns)):
                if dataset.columns[i] == variable:
                    for j in range(look_back_ini, look_back_fi-1):
                        dataset[dataset.columns[i]+'_'+str(j)] = dataset[dataset.columns[i]].shift(j)

            return dataset

        def do_windowing(self, data, look_back={-1:[25, 48]}):

            if look_back is not None:  # torna un np array no un list l'object storer

                # windowing de totes les no especificades individualment
                if -1 in look_back.keys():  # si indicador es -1 volen un grup
                    # volen fer un grup
                    aux = look_back[-1]  # recuperem els valors de la finestra per el grup
                
                    # recuperem les que es faran soles
                    keys = list()
                    for i in look_back.keys():
                        if i != -1:
                            keys.append(i)  # les anem posant a una llista totes les que tenim exepte el-1

                    dad = data.copy()  # copiem el dataset per no perdre les que niran soles
                    dad = dad.drop(columns=keys)  # eliminem les que van soles

                    # fem windowing de tot el grup
                    dad = self.windowing_grup(dad, aux[0], aux[1])

                    # afegim les que aviem tret
                    for i in keys:
                        dad[i] = data[i]

                else:
                    # cas de que no tinguem grups son totes individuals, ho preparem tot per fer les individuals
                    dad = data.copy()  # copiem el dataset
                    # les que es faran soles
                    keys = list()
                    for i in look_back.keys():
                        if i != -1:
                            keys.append(i)

                # windowing de la resta que es fan 1 a 1
                variables = [col for col in data.columns if col not in keys]
                for i in variables:
                    aux = look_back[-1]
                    dad = self.windowing_univariant(dad, aux[0], aux[1], i)

            else:
                # cas de no tenir windowing
                dad = data.copy()

            return dad
        
        def colinearity_remove(self, datasetin, y, level=0.9):
            """
            Elimina les coliniaritats entre les variables segons el nivell indicat.
            parametres:
                datasetin - pandas dataframe amb datetime com a index
                
                y- la variable objectiu (per comprovar que no ens la carreguem!)
                
                level - el percentatge de correlacio de pearson per carregar-nos variables. None per no fer res
                
            Retorna:
                dataset - El dataset - les variables eliminades 
                to_drop - les variables que ha eliminat
            
            """
            if level is None:
                dataset = datasetin
                to_drop = None
            else:
                # ens carreguem els atributs massa correlacionats (colinearity)
                corr_matrix = datasetin.corr().abs()
                upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
                to_drop = [column for column in upper.columns if any(upper[column] > level)]
                if np.array(to_drop == y).any():  # la classe sempre hi ha de ser!!! millor asegurem que hi sigui!
                    del to_drop[to_drop == y]
                datasetin.drop(to_drop, axis=1, inplace=True)
                dataset=datasetin.copy()
                
            return [dataset, to_drop]
        
        def Model(self, X, y, algorithm='RF', params=None, max_time=None):
            """
            Funcio que realitza un randomized search per trovar una bona configuracio de l'algorisme indicat, o directament es crea amb els parametres indicats
            
            X- np.array amb les dades
            y- np.array am les dades
            """
            ## primer carreguem el grid de parametres des de fitxer i imports
            import json
            with open(self.search_space_conf_file) as json_file:
                d = json.load(json_file)
             
            if params is None:
                #No tenim parametres els busquem. Utilitzarem del fitxer.

                #preparem les dades de train i test.
                from sklearn.model_selection import train_test_split
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3)#, shuffle=False) #no fem shufle. volem que aprengui tot el periode no nomes les ultimes observacions.
                
                #inicialitzem llibreries i MAE maxim trobat.
                from sklearn.model_selection import ParameterSampler
                from sklearn.metrics import mean_absolute_error
                import time
                best_mae = np.inf
                
                # preparem la llista d'algorismes que volem provar. (tots  o el que ens indiquen.)
                if algorithm is None:
                    # no ens passen res. els probem tots
                    algorithm_list = list(d.keys())
                    
                elif isinstance(algorithm, list):
                    # ens passen llista a probar
                    algorithm_list = algorithm
                    
                else:
                    # ens passen nomes 1
                    algorithm_list = [algorithm]
                
                # per cada algorisme a probar...
                for i in range(len(algorithm_list)):
                    
                    #Recuperem grid de parametres
                    random_grid = d[algorithm_list[i]][0]
                    
                    if max_time is None:
                        iters = d[algorithm_list[i]][1]
                    else:
                        iters = max_time
                    
                    #Els strings per fer l'import corresponent a l'algorisme
                    impo1 = d[algorithm_list[i]][2]
                    impo2 = d[algorithm_list[i]][3]

                    if self.debug:
                        print(" ")
                        print("Començant a optimitzar: " + algorithm_list[i] + '- Algorisme ' + str(algorithm_list.index(algorithm_list[i])+1) + ' de ' + str(len(algorithm_list)) + ' - Maxim comput aprox (segons): ' + str(iters))

                    # preparem mostra aleatroia de parametres
                    sampler = ParameterSampler(random_grid, n_iter=np.iinfo(np.int64).max)
                    
                    # recuperem la llibreria correcte
                    a = __import__(impo1, globals(), locals(), [impo2])
                    Forcast_algorithm = eval("a."+impo2)
                    
                    try:
                        #creem i evaluem els models 1 a 1
                        t = time.perf_counter()
                        if self.debug:
                            print("Maxim " + str(len(sampler))+ " configuracions a probar!")
                            j=0
                            
                        for params in sampler:
                            regr = Forcast_algorithm(**params)
                            pred_test = regr.fit(X_train, y_train).predict(X_test)
                            act = mean_absolute_error(y_test, pred_test)
                            if best_mae > act:
                                best_model = regr
                                best_mae = act

                            if self.debug:
                                print("\r", end="")
                                j=j+1
                                print(str(j) + "/"+  str(len(sampler)) +" Best MAE: " +str(best_mae) +" ("+ type(best_model).__name__ + ") Last MAE: " + str(act) + " Elapsed: "+ str(time.perf_counter() - t) +" s         ", end="")
                                
                            if (time.perf_counter() - t) > iters:
                                if self.debug:
                                    print("Algorisme " + algorithm_list[i] + '  -- Hem arribat a fi de temps de cerca.' )
                                break
                              
                    except Exception as e:
                        print("Warning: Algorisme " + algorithm_list[i] + '  -- Abortat Motiu:' + str(e) )
                
                best_model.fit(X, y)
                model = best_model
                score = best_mae
                
                return [model, score]
            
            else:
                # ens han especificat algorisme i parametres
                
                # importem la llibreria correcte
                try:
                    # Els strings per fer l'import corresponent a l'algorisme
                    impo1 = d[algorithm][2]
                    impo2 = d[algorithm][3]
                except:
                    raise ValueError('Undefined Forcasting Algorithm!')
                    
                #recuperem la llibreria correcte
                a = __import__(impo1,globals(), locals(),[impo2])
                Forcast_algorithm = eval("a."+impo2 )
                
                # posem els parametres que ens diuen i creem el model
                f=Forcast_algorithm()
                f.set_params(**params)
                f.fit(X,y)
                score = 'none'
                return [f, score]

        # Feature selection/reduction methods
        def treu_atrs(self,X,y, metode=None):
            """
            Fem una seleccio d'atributs
            
            X- np.array amb les dades
            y- np.array am les dades
            
            metode  -   None = no fa res
                        integer = selecciona el numero de features que indiquis
                        PCA = Aplica un PCA per comprimir el dataset.
            """
            if metode is None:
                model_select = []
                X_new = X
            elif metode == 'Tree':
                from sklearn.ensemble import ExtraTreesRegressor
                from sklearn.feature_selection import SelectFromModel
                clf = ExtraTreesRegressor(n_estimators=50)
                clf = clf.fit(X, y)
                model_select = SelectFromModel(clf, prefit=True)
                X_new = model_select.transform(X)
            elif type(metode) is int:                
                from sklearn.feature_selection import SelectKBest, f_classif
                model_select = SelectKBest(f_classif, k=metode)
                X_new = model_select.fit_transform(X, y)
            elif metode == 'PCA':
                from sklearn.decomposition import PCA
                model_select = PCA(n_components='mle')# Minka’s MLE is used to guess the dimension
                X_new = model_select.fit_transform(X)
            else:
                raise ValueError('Undefined atribute selection method!')
                
            return [model_select, X_new, y]

        """
        A partir d'aqui tenim les 2 funcions que controlen tot el funcionament del forecasting (create_model - crear i guardar el model, i forecasting - recuperar i utilitzar el model)
        """

        def train_model(self, data, y):
            
            logging.info("Iniciant el procés d'entrenament del model")
            
            # Convertir la columna 'timestamp' a format datetime si no ho és ja
            data['timestamp'] = pd.to_datetime(data['timestamp'])

            # Extraure característiques útils dels timestamps
            data['year'] = data['timestamp'].dt.year
            data['month'] = data['timestamp'].dt.month
            data['day'] = data['timestamp'].dt.day
            data['hour'] = data['timestamp'].dt.hour
            data['minute'] = data['timestamp'].dt.minute
            data['weekday'] = data['timestamp'].dt.weekday

            # Eliminar valors nuls de totes les dades abans de separar X i y
            data = data.dropna()

            # Eliminar la columna 'timestamp' de X i afegir les noves variables
            #X = data.drop(columns=[y])
            y_i = data[y]
            X = data.drop(columns=[y, 'timestamp'])

            # Dividim en train i test
            X_train, X_test, y_train, y_test = train_test_split(X, y_i, test_size=0.3, shuffle=False)  # no fem shufle. volem que aprengui tot el periode no nomes les ultimes observacions.
            
            # Escalar les dades
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Crear i entrenar model
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X_train_scaled, y_train)

            # avaluar el model
            score = model.score(X_test_scaled, y_test)
            logging.info(f"Model entrenat amb un score de {score}")

            self.db['model'] = model
            self.db['scaler'] = scaler
            logging.info("Scaler utilitzat per normalitzar les dades: " + str(scaler))
            logging.info("Model entrenat i guardat correctament")
            logging.info(f"Model carregat després del train: {model}")
            print("##################################################")

            return model
        
        def create_model(self, data, y, look_back={-1:[25,48]}, extra_vars={'variables':['Dia','Hora','Mes'], 'festius':['ES','CT']},
                         colinearity_remove_level=0.9, feature_selection='Tree', algorithm='RF', params=None, escalat=None, max_time=None):
            """
            funció que entrena el model i el guarda en un objecte storer.
            
            """
            
            # ja hauria d'estar fet pero per si de cas.
            #data = data.astype(float) --> no tenen perque ser tot floats!!! els trees accepten altres clases

            # Pas 1 - Fem el windowing
            dad = self.do_windowing(data, look_back)

            # Pas 2 - Creem variable dia_setmana, hora, mes
            dad = self.timestamp_to_attrs(dad, extra_vars)
            
            # Pas 3 - treiem colinearitats!
            [dad, to_drop] = self.colinearity_remove(dad, y, level=colinearity_remove_level)
            colinearity_remove_level_to_drop = to_drop

            # Pas 4 - treiem NaN! -- #TODO Fer opcional i permetre emplenar buits??
            dad.replace([np.inf, -np.inf], np.nan, inplace=True)
            X = dad.dropna()

            # Pas 5 - desfem el dataset i ens quedem nomes amb les matrius X i y
            nomy = y
            y = X[nomy]
            del X[nomy]
            
            # Pas 6 - Escalat
            X, scaler = self.scalate_data(X, escalat)

            # Pas 7 - Seleccionem atributs
            [model_select, X_new, y_new] = self.treu_atrs(X, y, feature_selection)

            # Pas 8 - Creem el model
            [model, score] = self.Model(X_new, y_new.values, algorithm, params, max_time=max_time)

            ####  Finalment un cop tenim el model configurat el guardem en un Object storer ###

            # Guardem els diferents models i configuracions que necessitarem per despres poder executar el forcast
            self.db['model'] = model
            self.db['scaler'] = scaler
            self.db['model_select'] = model_select
            self.db['colinearity_remove_level_to_drop'] = colinearity_remove_level_to_drop
            self.db['extra_vars'] = extra_vars
            self.db['look_back'] = look_back
            self.db['score'] = score
            self.db['objective'] = nomy
            
            if self.debug:  # m'interessa veure quan s'ha guardat un model, per saber per on va i que tot ha anat bé
                print('Model guardat!  Score:' + str(score))

        def forecast(self, data, y, model):
            """
            Processem les dades passant per diversos passos: windowing, afegir variables derivades, eliminar colinearitats,
            escalar, seleccionar atributs i realitzar la predicció amb el model carregat.

            Args:
                data (pd.DataFrame): Dades originals a processar.
                y (str): Nom de la columna que es vol predir.

            Returns:
                pd.DataFrame: Dades amb la predicció del model.
            """
            logging.info("Starting forecast.py prediction...")
            #logging.info(f"Primeres files de la columna '{y}':\n{data[y].head()}")
            #logging.info(f"Estadístiques de la columna '{y}':\n{data[y].describe()}")
            #logging.info(f"Nombre de valors nuls a la columna '{y}': {data[y].isnull().sum()}")
            #logging.info(f"Columnes disponibles al DataFrame: {data[y].head(20)}")
            
            # Recuperem els paràmetres del model
            #model = self.db['model'] # Carreguem el model de predicció
            model_select = self.db.get('model_select', []) #Carreguem el selector de característiques si existeix
            scaler = self.db['scaler'] # Carreguem l'escalador per normalitzar les dades
            logging.info("Scaler utilitzat per normalitzar les dades: " + str(scaler))
            colinearity_remove_level_to_drop = self.db.get('colinearity_remove_level_to_drop', []) # Columnes a eliminar per evitar colinealitats
            extra_vars = self.db.get('extra_vars', []) #Variables derivades addicionals
            look_back = {-1:[25,48]}
            #look_back = self.db.get('look_back', 0) # Nombre de passos enrere per fer el windowing

            ####### Now we have the model and the data, we can start the prediction process #######
            df = self.do_windowing(data, look_back) #Fem el windowing per preparar les dades en finestres temporals
            df = self.timestamp_to_attrs(df, extra_vars) #Afegim variables derivades de l'índex temporal

            # Eliminem columnes que provoquen colinealitat
            if colinearity_remove_level_to_drop:
                existing_cols = [col for col in colinearity_remove_level_to_drop if col in df.columns]
                df.drop(existing_cols, axis=1, inplace=True)

            # Eliminem la columna de la variable objectiu per evitar data leakage
            if y in df.columns:
                del df[y]
            else:
                raise ValueError(f"Column '{y}' not found in the dataset.")

            # Eliminem files amb NaN per evitar errors en la predicció
            if df.dropna().any().any():
                df = df.dropna()

            # Escalem les dades si hi ha un escalador definit
            if scaler:
                df.columns = [col.replace('value', 'state') for col in df.columns]
                df = pd.DataFrame(scaler.transform(df), index=df.index, columns=df.columns)

            # Seleccionem les característiques a utilitzar segons el selector del model
            if model_select:
                 df = model_select.transform(df) # Si hi ha selector, filtrem les característiques rellevants

            # Fem la predicció amb el model carregat
            out = pd.DataFrame(model.predict(df), columns=[y]) #Creem un DataFrame amb la predicció

            return out # Retornem les dades amb la predicció

        def timestamp_to_attrs(self, dad, extra_vars):
            """
            Afegeix columnes derivades de l'índex temporal al DataFrame `dad` segons les opcions indicades a `extra_vars`.

            Args:
                dad (pd.DataFrame): DataFrame amb un índex temporal.
                extra_vars (dict): Diccionari amb opcions per generar columnes addicionals. 
                                Possibles claus: 'variables', 'festius'.

            Returns:
                pd.DataFrame: El mateix DataFrame amb les noves columnes afegides.
            """

            dad.index = pd.to_datetime(dad.index)
            logging.info(dad.head(20))


            if not extra_vars:
                # Si extra_vars és None o buit, no cal fer res
                return dad

            # Afegim columnes basades en l'índex temporal
            if 'variables' in extra_vars:
                for variable in extra_vars['variables']:
                    if variable == 'Dia':
                        dad['Dia'] = dad.index.dayofweek  # Dia de la setmana (0=Dll, 6=Dg)
                    elif variable == 'Hora':
                        dad['Hora'] = dad.index.hour  # Hora del dia
                    elif variable == 'Mes':
                        dad['Mes'] = dad.index.month  # Mes de l'any
                    elif variable == 'Minut':
                        dad['Minut'] = dad.index.minute  # Minut de l'hora

            # Afegim columnes per a dies festius
            if 'festius' in extra_vars:
                festius = extra_vars['festius']
                if len(festius) == 1:
                    # Festius d'un sol país
                    h = holidays.country_holidays(festius[0])
                elif len(festius) == 2:
                    # Festius d'un país amb una regió específica
                    h = holidays.country_holidays(festius[0], festius[1])
                else:
                    raise ValueError("La clau 'festius' només suporta 1 o 2 paràmetres (país i opcionalment regió).")

                # Afegeix una columna booleana indicant si cada dia és festiu
                dad['festius'] = dad.index.strftime('%Y-%m-%d').isin(h)

            logging.info(dad.head(20))
            #dad.drop(columns=['timestamp'], inplace=True)

            return dad

        def scalate_data(self, data, escalat):

            dad = data.copy()
            scaler = None
            if escalat != None:
                if escalat == 'MINMAX':
                    from sklearn.preprocessing import MinMaxScaler
                    scaler = MinMaxScaler()
                    scaler.fit(data)
                    dad = scaler.transform(data)
                elif escalat == 'Robust':
                    from sklearn.preprocessing import RobustScaler
                    scaler = RobustScaler()
                    scaler.fit(data)
                    dad = scaler.transform(data)

                elif escalat == 'Standard':
                    from sklearn.preprocessing import StandardScaler
                    scaler = StandardScaler()
                    scaler.fit(data)
                    dad = scaler.transform(data)

                else:
                    raise ValueError('Undefined atribute selection method!')
            else:
                scaler = None

            return dad, scaler

        def save_model(self, filename='Model-data.joblib'):
            joblib.dump(self.db, filename)
            print("Model guardat al fitxer " + filename)

        def load_model(self, filename):
            self.db = joblib.load(filename)
