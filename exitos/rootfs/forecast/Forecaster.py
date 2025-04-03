import joblib
import numpy as np
import pandas as pd
import holidays
import logging
import os
import glob


logger = logging.getLogger("exitOS")


class Forecaster:
    def __init__(self, debug = False):
        """
        Constructor per defecte del Forecaster
        """

        self.debug = debug
        self.search_space_config_file = 'resources/search_space.conf'
        self.db = dict()


    @staticmethod
    def windowing_group(dataset, look_back_start = 24, look_back_end = 48):
        """
        Funció per crear les variables del windowing. \n
        Treballa sobre un dataset i inclou la variable objectiu. \n
        Les variables creades es diràn com les originals (legacy) i s'afagirà '_' amb el número de desplaçament. \n
        Es tindràn en compte les hores en el rang [ini,fi)

        :param dataset: Dataframe amb datetime com a índex
        :type dataset: pd.DataFrame
        :param look_back_start: On comença la finestra ( 24 -> el dia anterior si és horari)
        :param look_back_end: On acaba el número d'observacions (48 -> el dia anterior si és horari)
        :return: Dataset amb les cariables desplaçades en columnes noves
        :rtype: pd.DataFrame
        """

        ds = dataset.copy()
        for i in range(0, len(ds.columns)):
            if ds.columns[i] != 'timestamp':
                for j in range(look_back_start, look_back_end):
                    ds[ds.columns[i] + '_' + str(j)] = ds[ds.columns[i]].shift(j)

        return ds


    @staticmethod
    def windowing_univariant(dataset, look_back_start = 24, look_back_end = 48, variable =''):
        """
        Funció per crear les variables del windowing. \n
        Treballa sobre un dataset i inclou la variable objectiu. \n
        Les variables creades es diràn com les originals (legacy) i s'afagirà '_' amb el número de desplaçament. \n
        Es tindràn en compte les hores en el rang [ini,fi)

        :param dataset: Dataframe amb datetime com a índex
        :type dataset: pd.DataFrame
        :param look_back_start: On comença la finestra ( 24 -> el dia anterior si és horari)
        :param look_back_end: On acaba el número d'observacions (48 -> el dia anterior si és horari)
        :param variable: Variable a transformar en variables del windowing.
        :return: Dataset amb les cariables desplaçades en columnes noves
        :rtype: pd.DataFrame
        """

        ds = dataset.copy()
        for i in range(0, len(ds.columns)):
            if ds.columns[i] == variable:
                for j in range(look_back_start, look_back_end-1):
                    ds[ds.columns[i] + '_' + str(j)] = ds[ds.columns[i]].shift(j)

        return ds


    def do_windowing(self, data, look_back={-1: [25, 48]}):
        """
        Aplica el Windowing en consequencia al look_back indicat.\n
        - None -> no aplica el windowing \n
        - Diccionari on la clau és la variable a fer windowing i el valor la finestra que s'ha d'aplicar \n
        - Les claus son Strings, indicant el nom de la columna a aplicar windowing
        - Si com a clau es dona -1, la finestra aplicara a totes les variables NO especificades individualment.
        - Els valors són els que defineixen la finestra a aplicar, i poden ser:
            - [ini, fi]
            - [ini, fi, salt]
        :param data: dataframe de dades
        :param look_back: Windowing a aplicar
        :return: dataframe de dades preparades per el model de forecasting.
        """
        if look_back is not None:
            #windowing  de tots els grups (NO individuals)
            if -1 in look_back.keys(): #si l'indicador és -1 volem un grup
                aux = look_back[-1] #recuperem els valors de la finestra pel grup

                #recuperem les que es faran soles
                keys = list()
                for i in look_back.keys():
                    if i != -1:
                        keys.append(i)

                dad = data.copy() #copiem el dataset per no perdre les que aniran soles
                dad = dad.drop(columns=keys) #eliminem les que van soles

                #windowing de tot el grup
                dad = self.windowing_group(dad, aux[0], aux[1])

                #afegim les que haviem tret abans
                for i in keys:
                    dad[i] = data[i]

            else:
                #cas de que no tinguem grups, son tots individuals
                dad = data.copy() #copiem el dataset
                keys = list()
                for i in look_back.keys():
                    if i != -1:
                        keys.append(i)

            #windowing de la resta que es fan 1 a 1
            variables = [col for col in data.columns if col not in keys]
            for i in variables:
                if i.startswith('timestamp'): continue
                aux = look_back[-1]
                dad = self.windowing_univariant(dad, aux[0], aux[1], i)
        else:
            #cas de no tenir windowing
            dad = data.copy()

        return dad


    @staticmethod
    def timestamp_to_attrs(dad, extra_vars, meteo_data:pd.DataFrame):
        """
        Afageix columnes derivades de l'índex temporal al DataFreame 'dad' segons les opcions indicades en 'extra_vars'. \n'
        :param dad: Dataframe amb un índex timestamp
        :type dad: pd.DataFrame
        :param extra_vars: Diccionari amb opcions per a generar columnes adicionals ('variables', 'festius')
        :type extra_vars: dict
        :return: El mateix DataFrame amb les noves columnes afegides.
        """

        if 'timestamp' in dad.columns:
            dad.index = pd.to_datetime(dad['timestamp'])
        logger.info(f"DAD HEAD 1 (timestamps_to_attrs()){dad.head(20)}")


        if not extra_vars:
            #si extra_vars és None o buit, no cal fer res
            return dad

        #afegim columnes basades en l'índex temporal
        if 'variables' in extra_vars:
            for var in extra_vars['variables']:
                if var == 'Dia':
                    dad['Dia'] = dad.index.dayofweek #Dia de la setmana (0 = Dll, 6 = Dg)
                elif var == 'Hora':
                    dad['Hora'] = dad.index.hour #Hora del dia
                elif var == 'Mes':
                    dad['Mes'] = dad.index.month # Mes de l'any
                elif var == 'Minut':
                    dad['Minut'] = dad.index.minute # Minut de l'hora

        #Afegim columnes per a dies festius
        if 'festius' in extra_vars:
            festius = extra_vars['festius']
            if len(festius) == 1:
                #Festius d'un sol país
                h = holidays.country_holidays(festius[0])
            elif len(festius) == 2:
                #festius d'un sol país amb una regió específica
                h = holidays.country_holidays(festius[0], festius[1])
            else:
                raise ValueError("La clau 'festius' només suporta 1 o 2 paràmetres (país i opcionalment regió)")

            #Afageix una columna booleana indicant si cada dia es festiu
            dad['festius'] = dad.index.strftime('%Y-%m-%d').isin(h)

        if 'timestamp' in dad.columns:
            dad.drop(columns=['timestamp'], inplace=True)
        logger.info(f"DAD HEAD 2 (timestamps_to_attrs()) {dad.head(20)}")

        return dad


    @staticmethod
    def colinearity_remove(data, y, level=0.9):
        """
        Elimina les colinearitats entre les variables segons el nivell indicat
        :param data: Dataframe amb datetime com a índex
        :type data: pd.DataFrame
        :param y: Variable objectiu (per mirar que no la eliminem!)
        :param level: el percentatge de correlació de pearson per eliminar variables. None per no fer res
        :return:
            - dataset - Dataset amb les variables eliminades
            - to_drop - Les variables que ha eliminat
        """

        if level is None:
            dataset = data
            to_drop = None
        else:
            #eliminem els atributs massa correlacionats
            corr_matrix = data.corr().abs()
            upper = corr_matrix.where(
                np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
            )
            to_drop = [column for column in upper.columns if any(upper[column] > level)]
            if np.array(to_drop == y).any():
                del to_drop[to_drop == y]
            data.drop(to_drop, axis=1, inplace=True)
            dataset = data.copy()

        return [dataset, to_drop]


    @staticmethod
    def scalate_data(data, input_scaler=None):
        """
        Escala les dades del dataset
        :param data: Dataset a escalar
        :param scaler: Mètode a usar per escalar
        :return: [Dataset , scaler]
        """
        dad = data.copy()
        scaler = None

        if input_scaler is not None:
            if input_scaler == 'MINMAX':
                from sklearn.preprocessing import MinMaxScaler
                scaler = MinMaxScaler()
                scaler.fit(data)
                dad = scaler.transform(dad)
            elif input_scaler == 'Robust':
                from sklearn.preprocessing import RobustScaler
                scaler = RobustScaler()
                scaler.fit(data)
                dad = scaler.transform(data)
            elif input_scaler == 'Standard':
                from sklearn.preprocessing import StandardScaler
                scaler = StandardScaler()
                scaler.fit(data)
                dad = scaler.transform(dad)
            else:
                raise ValueError('Atribut Scaler no definit')
        else:
            scaler = None

        return dad, scaler


    @staticmethod
    def get_attribs(X, y, method = None):
        """
        Fa una selecció d'atributs
        :param X: Array amb les dades
        :param y: Array amb les dades
        :param method:
            - None: No fa res
            - integer: selecciona el número de features que s'indiquin
            - PCA: aplica un PCA per comprimir el dataset
        :return:
        """

        if method is None:
            model_select = []
            X_new = X
        elif method == 'Tree':
            from sklearn.ensemble import ExtraTreesRegressor
            from sklearn.feature_selection import SelectFromModel

            clf = ExtraTreesRegressor(n_estimators=50)
            clf = clf.fit(X, y)
            model_select = SelectFromModel(clf, prefit=True)
            X_new = model_select.transform(X)
        elif type(method) == int:
            from sklearn.feature_selection import SelectKBest, f_classif
            model_select = SelectKBest(f_classif, k=method)
            X_new = model_select.fit_transform(X, y)
        else:
            raise ValueError('Atribut de mètode de selecció no definit')

        return [model_select, X_new, y]


    def Model(self, X, y, algorithm="RF", params=None, max_time=None):
        """
        Realitza un randomized search per trovar una bona configuració de l'algorisme indicat, o directament, es crea amb els paràmetres indicats.
        :param X:
        :param y:
        :param algorithm:
        :param params:
        :param max_time:
        :return:
        """

        import json


        with open(self.search_space_config_file) as json_file:
            d = json.load(json_file)

        if type(params) == dict:
            try:
                impo1 = d[algorithm][2]
                impo2 = d[algorithm][3]
            except:
                raise ValueError("Undefined Firecasting Algorithm!")

            a = __import__(impo1, globals(), locals(), [impo2])
            forecast_algorithm = eval("a. " + impo2)

            f = forecast_algorithm()
            f.set_params(**params)
            f.fit(X, y)
            score = 'none'
            return [f, score]
        elif  params is None: #no tenim paràmetres. Els busquem
            from sklearn.model_selection import train_test_split
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, shuffle=False)

            from sklearn.model_selection import ParameterSampler
            from sklearn.metrics import mean_absolute_error
            import time

            best_mae = np.inf

            #preparem la llista d'algorismes que volem provar
            if algorithm is None:
                #si no ens passen res els probem tots
                algorithm_list = list(d.keys())
            elif isinstance(algorithm, list):
                #passen una llista a probar
                algorithm_list = algorithm
            else:
                #ens passen només 1
                algorithm_list = [algorithm]

            #per cada algorisme a probar....
            for i in range(len(algorithm_list)):
                random_grid = d[algorithm_list[i]][0]

                if max_time is None: iters = d[algorithm_list[i]][1]
                else: iters = max_time

                impo1 = d[algorithm_list[i]][2]
                impo2 = d[algorithm_list[i]][3]

                if self.debug:
                    logger.info("  ")
                    logger.info(f"Començant a optimitzar:  {algorithm_list[i]}  - Algorisme {str(algorithm_list.index(algorithm_list[i]) + 1)}  de  {str(len(algorithm_list))} - Maxim comput aprox (segons): {str(iters)}")



                sampler = ParameterSampler(random_grid, n_iter=np.iinfo(np.int64).max)

                a = __import__(impo1, globals(), locals(), [impo2]) # equivalent a (import sklearn.svm as a) dinamicament
                forecast_algorithm = eval("a. "+impo2)

                try:
                    #creem i evaluem els models 1 a 1
                    t = time.perf_counter()

                    if self.debug:
                        logger.debug(f"Maxim {str(len(sampler))}  configuracions a probar!")
                        j = 0

                    best_model = None

                    for params in sampler:
                        regr = forecast_algorithm(**params)
                        pred_test = regr.fit(X_train, y_train).predict(X_test)
                        act = mean_absolute_error(y_test, pred_test)
                        if best_mae > act:
                            best_model = regr
                            best_mae = act

                        if self.debug:
                            logger.info("\r")
                            j += 1
                            logger.debug(f"{str(j)} / {str(len(sampler))} Best MAE: {str(best_mae)} ({type(best_model).__name__}) Last MAE: {str(act)}  Elapsed: {str(time.perf_counter() - t)} s ")

                        if (time.perf_counter() - t) > iters:
                            if self.debug:
                                logger.debug("Algorisme " + algorithm_list[i] + " -- Abortat per Maxim comput aprox (segons): " + str(iters))
                                break

                except Exception as e:
                    logger.warning(f"WARNING: Algorisme {algorithm_list[i]},  -- Abortat per Motiu: {str(e)}")

                if best_model is not None:
                    best_model.fit(X, y)
                    model = best_model
                    score = best_mae
                else:
                    model = None
                    score = np.inf

                return [model, score]
        else:
            raise ValueError('Paràmetres en format incorrecte!')


    def create_model(self, data, y, look_back={-1: [25, 48]},
                     extra_vars={'variables': ['Dia', 'Hora', 'Mes'], 'festius': ['ES', 'CT']},
                     colinearity_remove_level=0.9, feature_selection='Tree', algorithm='RF', params=None, escalat=None,
                     max_time=None, filename='savedModel', meteo_data:pd.DataFrame = None,):
        """
        Funció per crear, guardar i configurar el model de forecasting.

        :param meteo_data:
        :param filename:
        :param max_time:
        :param escalat:
        :param params:
        :param algorithm:
        :param feature_selection:
        :param extra_vars:
        :param colinearity_remove_level:
        :param data: Dataframe amb datetime com a índex
        :param y: Nom de la columna amb la variable a predir
        :param look_back: #TODO

        """

        meteo_data['timestamp'] = pd.to_datetime(meteo_data['timestamp']).dt.tz_localize(None).dt.floor('h')
        data['timestamp'] = pd.to_datetime(data['timestamp']).dt.tz_localize(None).dt.floor('h')

        mergedData = pd.merge(data, meteo_data, on='timestamp', how='inner')

        #PAS 1 - Fer el Windowing
        dad = self.do_windowing(mergedData, look_back)

        #PAS 2 - Crear variable dia_setmana, hora, mes i meteoData
        dad = self.timestamp_to_attrs(dad, extra_vars, meteo_data)

        #PAS 3 - Treure Colinearitats
        [dad, to_drop] = self.colinearity_remove(dad, y, level=colinearity_remove_level)
        colinearity_remove_level_to_drop = to_drop

        #PAS 4 - Treure NaN
        dad.replace([np.inf, -np.inf], np.nan, inplace=True)
        X = dad.dropna()

        #PAS 5 - Desfer el dataset i guardar matrius X i y
        nomy = y
        y = X[nomy]
        del X[nomy]


        #PAS 6 - Escalat
        X, scaler = self.scalate_data(X, escalat)

        #PAS 7 - Seleccionar atributs
        [model_select, X_new, y_new] = self.get_attribs(X, y, feature_selection)

        #PAS 8 - Crear el model
        [model, score] = self.Model(X_new, y_new.values, algorithm, params, max_time=max_time)

        #PAS 9 - Guardar el model
        self.db['model'] = model
        self.db['scaler'] = scaler
        self.db['model_select'] = model_select
        self.db['colinearity_remove_level_to_drop'] = colinearity_remove_level_to_drop
        self.db['extra_vars'] = extra_vars
        self.db['look_back'] = look_back
        self.db['score'] = score
        self.db['objective'] = nomy
        self.db['initial_data'] = mergedData

        self.save_model(filename)

        if self.debug:
            logger.debug('Model guardat! Score: ' + str(score))

    def forecast(self, data, y, model):
        """

        :return:
        """
        logger.info("Iniciant forecast...")

        # PAS 1 - Obtenir els valors del model
        model_select = self.db.get('model_select', []) #intenta obtenir model_select, si no existeix retorna []
        scaler = self.db['scaler']
        colinearity_remove_level_to_drop = self.db.get('colinearity_remove_level_to_drop', [])
        extra_vars = self.db.get('extra_vars', [])
        look_back = self.db.get('look_back', {-1:[25,48]})

        # PAS 2 - Aplicar el windowing
        df = self.do_windowing(data, look_back)

        # PAS 3 - Afegir variables derivades de l'índex temporal {dia, hora, mes, ...}
        df = self.timestamp_to_attrs(df, extra_vars)

        # PAS 4 - Eliminar colinearitats
        if colinearity_remove_level_to_drop:
            existing_cols = [col for col in colinearity_remove_level_to_drop if col in df.columns]
            df.drop(existing_cols, axis=1, inplace=True)

        # PAS 5 - Eliminar la y
        if y in df.columns:
            del df[y]
        else:
            raise ValueError(f"Columna {y} no trobada en el dataset")

        # PAS 6 - Elinimar els NaN
        if df.dropna().any().any():
            df = df.dropna()

        # PAS 7 - Escalar les dades
        if scaler:
            df.columns = [col.replace('value', 'state') for col in df.columns]
            df = pd.DataFrame(scaler.transform(df), index=df.index, columns=df.columns)

        # PAS 8 - Seleccionar característiques a usar segons el selector del model
        if model_select:
            df = model_select.transform(df)

        # PAS 9 - Fer la predicció
        out = pd.DataFrame(model.predict(df), columns=[y])

        return out





    def save_model(self, model_filename):
        """
        Guarda el model en un arxiu .pkl i l'elimina de la base de daades interna del forecast (self.db)
        :param model_filename: Nom que es vol donar al fitxer, si és nul serà "savedModel"
        """
        joblib.dump(self.db, "/share/exitos/"+ model_filename + '.pkl')
        logger.warning(glob.glob("/share/exitos/*"))
        logger.info(f"Model guardat al fitxer {model_filename}.pkl")

        self.db.clear()

    def load_model(self, model_filename):
        self.db = joblib.load(model_filename + '.pkl')
        logger.info(f"Model carregat del fitxer {model_filename}.pkl")

