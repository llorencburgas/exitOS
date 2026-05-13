from datetime import timedelta
import time

import joblib
import numpy as np
import pandas as pd
import holidays
import logging
import os
import glob
import requests
import json
from sklearn.model_selection import train_test_split, ParameterSampler
from sklearn.metrics import mean_absolute_error

from forecast.ForecastMetrics import ForecastMetrics

logger = logging.getLogger("exitOS")


class Forecaster:
    def __init__(self, debug=False):
        """
        Inicialitza una nova instància de la classe Forecaster i configura l'entorn de treball.

        Estableix les rutes dels fitxers de configuració i el directori de magatzem dels models
        en funció de si l'execució es realitza dins d'un entorn Hass.io o en local. També
        inicialitza el diccionari de metadades de la base de dades i el mòdul de mètriques.

        :param debug: Booleà per activar o desactivar els missatges de depuració.
        """

        self.debug = debug
        self.search_space_config_file = 'resources/search_space.conf'
        self.db = dict()
        self.metrics = ForecastMetrics(debug=debug)

        if "HASSIO_TOKEN" in os.environ:
            self.models_filepath = "share/exitos/"
        else:
            self.models_filepath = "./share/exitos/"

    @staticmethod
    def windowing_group(dataset, look_back_start=24, look_back_end=48):
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
        shifted_columns = {}

        for col in ds.columns:
            if col != 'timestamp':
                for j in range(look_back_start, look_back_end):
                    shifted_columns[f"{col}_{j}"] = ds[col].shift(j)

        ds = pd.concat([ds, pd.DataFrame(shifted_columns, index=ds.index)], axis=1)

        return ds

    @staticmethod
    def windowing_univariant(dataset, look_back_start=24, look_back_end=48, variable=''):
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
        :return: Dataset amb les variables desplaçades en columnes noves
        :rtype: pd.DataFrame
        """

        ds = dataset.copy()
        for i in range(0, len(ds.columns)):
            if ds.columns[i] == variable:
                for j in range(look_back_start, look_back_end - 1):
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
            # windowing  de tots els grups (NO individuals)
            if -1 in look_back.keys():  # si l'indicador és -1 volem un grup
                aux = look_back[-1]  # recuperem els valors de la finestra pel grup

                # recuperem les que es faran soles
                keys = list()
                for i in look_back.keys():
                    if i != -1:
                        keys.append(i)

                dad = data.copy()  # copiem el dataset per no perdre les que aniran soles
                dad = dad.drop(columns=keys)  # eliminem les que van soles

                # windowing de tot el grup
                dad = self.windowing_group(dad, aux[0], aux[1])

                # afegim les que haviem tret abans
                for i in keys:
                    dad[i] = data[i]

            else:
                # cas de que no tinguem grups, son tots individuals
                dad = data.copy()  # copiem el dataset
                keys = list()
                for i in look_back.keys():
                    if i != -1:
                        keys.append(i)

            # windowing de la resta que es fan 1 a 1
            variables = [col for col in data.columns if col not in keys]
            for i in variables:
                if i.startswith('timestamp'): continue
                aux = look_back[-1]
                dad = self.windowing_univariant(dad, aux[0], aux[1], i)
        else:
            # cas de no tenir windowing
            dad = data.copy()

        return dad

    @staticmethod
    def timestamp_to_attrs(dad, extra_vars):
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

        if not extra_vars:
            # si extra_vars és None o buit, no cal fer res
            return dad

        # afegim columnes basades en l'índex temporal
        if 'variables' in extra_vars:
            for var in extra_vars['variables']:
                if var == 'Dia':
                    dad['Dia'] = dad.index.dayofweek  # Dia de la setmana (0 = Dll, 6 = Dg)
                elif var == 'Hora':
                    dad['Hora'] = dad.index.hour  # Hora del dia
                elif var == 'Mes':
                    dad['Mes'] = dad.index.month  # Mes de l'any
                elif var == 'Minut':
                    dad['Minut'] = dad.index.minute  # Minut de l'hora

        # Afegim columnes per a dies festius
        if 'festius' in extra_vars:
            festius = extra_vars['festius']

            # Necessitem passar els anys explícitament per a que holidays generi les dades
            years = dad.index.year.unique()

            if len(festius) == 1:
                # Festius d'un sol país
                h = holidays.country_holidays(festius[0], years=years)
            elif len(festius) == 2:
                # festius d'un sol país amb una regió específica
                h = holidays.country_holidays(festius[0], festius[1], years=years)
            else:
                raise ValueError("La clau 'festius' només suporta 1 o 2 paràmetres (país i opcionalment regió)")

            # Afageix una columna booleana indicant si cada dia es festiu
            # Convertim les dates festives a string per comparar amb strftime (evita error Str vs Date)
            h_str = {d.strftime('%Y-%m-%d') for d in h.keys()}
            dad['festius'] = dad.index.strftime('%Y-%m-%d').isin(h_str)

        if 'timestamp' in dad.columns:
            dad.drop(columns=['timestamp'], inplace=True)

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
            # eliminem els atributs massa correlacionats
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
        Aplica una normalització o estandardització a les columnes del dataset.

        Utilitza diferents mètodes de la llibreria *scikit-learn* per transformar les dades
        segons el tipus d'escalador seleccionat (MinMaxScaler, RobustScaler o StandardScaler),
        mantenint l'índex i els noms de les columnes originals.

        :param data: DataFrame original amb les dades numèriques a transformar.
        :param input_scaler: String que defineix el mètode ('minmax', 'robust', 'standard' o None).
        :return: Una llista que conté el DataFrame escalat i l'objecte scaler utilitzat.
        :raises ValueError: Si el tipus d'escalador especificat no és reconegut. En cas contrari:
        (
            pd.DataFrame([[float, ...], ...]),
            <sklearn.preprocessing.scaler_object> or None
        )
        """
        dad = data.copy()
        scaler = None

        if input_scaler is not None:
            if input_scaler == 'minmax':
                from sklearn.preprocessing import MinMaxScaler
                scaler = MinMaxScaler()
                dad = pd.DataFrame(scaler.fit_transform(data), index=data.index, columns=data.columns)
            elif input_scaler == 'robust':
                from sklearn.preprocessing import RobustScaler
                scaler = RobustScaler()
                dad = pd.DataFrame(scaler.fit_transform(data), index=data.index, columns=data.columns)
            elif input_scaler == 'standard':
                from sklearn.preprocessing import StandardScaler
                scaler = StandardScaler()
                dad = pd.DataFrame(scaler.fit_transform(data), index=data.index, columns=data.columns)
            else:
                raise ValueError('Atribut Scaler no definit')
        else:
            scaler = None

        return dad, scaler

    @staticmethod
    def get_attribs(X, y, method=None):
        """
        Realitza una selecció o reducció de característiques (features) del dataset.

        Segons el mètode escollit, pot mantenir totes les variables, seleccionar les més
        importants mitjançant un arbre de decisió (ExtraTreesRegressor) o escollir les
        'k' millors basant-se en proves estadístiques univariants.

        :param X: Matriu de característiques d'entrada (features).
        :param y: Vector de la variable objectiu (target).
        :param method: Mètode de selecció (None, 'Tree' o un enter per a SelectKBest).
        :return: Una llista que conté el model de selecció aplicat, la nova matriu X reduïda i la y original.
        :raises ValueError: Si el mètode especificat no és vàlid.
        [
            <sklearn.feature_selection_object> or [],
            np.array([[float, ...], ...]),
            np.array([float, ...])
        ]
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

    def Model(self, X, y, algorithm=None, params=None, max_time=None):
        """
        Entrena o cerca la millor configuració d'un algorisme de predicció.

        Si es proporcionen paràmetres, entrena el model directament. Si no, realitza una
        cerca aleatòria (Randomized Search) sobre l'espai definit al fitxer de configuració,
        avalua els models amb MAE (Mean Absolute Error) i selecciona el millor dins dels
        límit de temps establerts.

        :param X: Matriu de característiques d'entrada.
        :param y: Vector de la variable objectiu.
        :param algorithm: Nom o llista d'algorismes a utilitzar (si és None, es proven tots).
        :param params: Diccionari de paràmetres concrets o None per activar la cerca automàtica.
        :param max_time: Temps màxim d'execució en segons per a l'optimització de cada algorisme.
        :return: Una llista que conté el model entrenat i la seva puntuació -> MAE o 'none'.
        :raises ValueError: Si l'algorisme no està definit o el format dels paràmetres és invàlid.

        [
            <sklearn.model_object>,
            float  # (Puntuació MAE o 'none')
        ]
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
        elif params is None:  # no tenim paràmetres. Els busquem
            from sklearn.model_selection import train_test_split
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, shuffle=False)

            from sklearn.model_selection import ParameterSampler
            from sklearn.metrics import mean_absolute_error
            import time

            best_mae = np.inf

            # preparem la llista d'algorismes que volem provar
            if algorithm is None:
                # si no ens passen res els probem tots
                algorithm_list = list(d.keys())
            elif isinstance(algorithm, list):
                # passen una llista a probar
                algorithm_list = algorithm
            else:
                # ens passen només 1
                algorithm_list = [algorithm]

            best_overall_model = None
            best_overall_score = float("inf")
            # per cada algorisme a probar....
            for i in range(len(algorithm_list)):
                random_grid = d[algorithm_list[i]][0]

                if max_time is None:
                    iters = d[algorithm_list[i]][1]
                else:
                    iters = max_time

                impo1 = d[algorithm_list[i]][2]
                impo2 = d[algorithm_list[i]][3]

                if self.debug:
                    logger.info("  ")
                    logger.info(
                        f"Començant a optimitzar:  {algorithm_list[i]}  - Algorisme {str(algorithm_list.index(algorithm_list[i]) + 1)}  de  {str(len(algorithm_list))} - Maxim comput aprox (segons): {str(iters)}")

                sampler = ParameterSampler(random_grid, n_iter=np.iinfo(np.int64).max)

                a = __import__(impo1, globals(), locals(),
                               [impo2])  # equivalent a (import sklearn.svm as a) dinamicament
                forecast_algorithm = eval("a. " + impo2)

                try:
                    # creem i evaluem els models 1 a 1
                    t = time.perf_counter()

                    if self.debug:
                        logger.debug(f"Maxim {str(len(sampler))}  configuracions a probar!")
                        j = 0

                    best_model = None
                    best_mae = float("inf")

                    for params in sampler:
                        try:
                            regr = forecast_algorithm(**params)
                        except Exception as e:
                            logger.warning(f"Failed with params: {params}")
                            continue

                        pred_test = regr.fit(X_train, y_train).predict(X_test)
                        act = mean_absolute_error(y_test, pred_test)
                        if best_mae > act:
                            best_model = regr
                            best_mae = act

                        if self.debug:
                            logger.info("\r")
                            j += 1
                            logger.debug(
                                f"{str(j)} / {str(len(sampler))} Best MAE: {str(best_mae)} ({type(best_model).__name__}) Last MAE: {str(act)}  Elapsed: {str(time.perf_counter() - t)} s ")

                        if (time.perf_counter() - t) > iters:
                            if self.debug:
                                logger.debug("Algorisme " + algorithm_list[
                                    i] + " -- Abortat per Maxim comput aprox (segons): " + str(iters))
                                break

                except Exception as e:
                    logger.warning(f"WARNING: Algorisme {algorithm_list[i]},  -- Abortat per Motiu: {str(e)}")
                    continue

                if best_model is not None:
                    best_model.fit(X, y)
                    if best_mae < best_overall_score:
                        best_overall_model = best_model
                        best_overall_score = best_mae

            return [best_overall_model, best_overall_score]
        else:
            raise ValueError('Paràmetres en format incorrecte!')

    @staticmethod
    def prepare_dataframes(sensor, meteo, extra_sensors):
        """
        Consolida les dades del sensor principal, meteorologia i sensors extra en un únic dataset.

        Normalitza tots els conjunts de dades eliminant les zones horàries i aplicant un
        remostreig (resample) horari basat en la mitjana. Finalment, fusiona les dades
        mitjançant un 'outer join' per l'índex temporal.

        :param sensor: DataFrame del sensor objectiu (target).
        :param meteo: DataFrame amb dades meteorològiques o None.
        :param extra_sensors: Diccionari de DataFrames amb sensors addicionals.
        :return: DataFrame unificat amb el timestamp com a columna i valors agregats per hores.
        {
            "timestamp": [datetime, ...],
            "value": [float, ...],
            "temperature_2m": [float, ...],
            "extra_sensor_col": [float, ...]
        }
        """
        merged_data = pd.DataFrame()

        # 1. Preparar sensor principal (Target)
        if sensor is not None and not sensor.empty:
            sensor = sensor.copy() # Evitar SettingWithCopy warning
            sensor['timestamp'] = pd.to_datetime(sensor['timestamp']).dt.tz_localize(None)
            sensor.set_index('timestamp', inplace=True)
            
            # Assegurar que 'value' és numèric
            if 'value' in sensor.columns:
                sensor['value'] = pd.to_numeric(sensor['value'], errors='coerce')
            
            # Resample horari fent la mitjana (només columnes numèriques per evitar errors)
            sensor = sensor.resample('h').mean(numeric_only=True)
            merged_data = sensor.copy()
        
        # 2. Preparar dades meteo
        if meteo is not None and not meteo.empty:
            meteo = meteo.copy()
            meteo['timestamp'] = pd.to_datetime(meteo['timestamp']).dt.tz_localize(None)
            meteo.set_index('timestamp', inplace=True)
            # Meteo ja sol venir horària, però per seguretat fem resample
            meteo = meteo.resample('h').mean(numeric_only=True)
            
            if merged_data.empty:
                merged_data = meteo
            else:
                merged_data = pd.merge(merged_data, meteo, left_index=True, right_index=True, how='outer')

        # 3. Preparar sensors extra
        if extra_sensors is not None:
             for key, df_extra in extra_sensors.items():
                if df_extra is not None and not df_extra.empty:
                    df = df_extra.copy()
                    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
                    df.set_index('timestamp', inplace=True)
                    
                    # Assegurar que 'value' és numèric
                    if 'value' in df.columns:
                        df['value'] = pd.to_numeric(df['value'], errors='coerce')

                    # Resample horari
                    df = df.resample('h').mean(numeric_only=True)
                    
                    if merged_data.empty:
                        merged_data = df
                    else:
                        merged_data = pd.merge(merged_data, df, left_index=True, right_index=True, how='outer')

        # Si després de tot no tenim dades, retornem el sensor original processat (o buit)
        if merged_data.empty:
            return pd.DataFrame()

        # Rename value_x to value if needed (fix legacy merging naming issues)
        if "value" not in merged_data.columns and "value_x" in merged_data.columns:
             merged_data.rename(columns={'value_x': 'value'}, inplace=True)

        # Reset index per tornar a tenir timestamp com a columna (compatible amb la resta de codi)
        merged_data.reset_index(inplace=True)
        
        return merged_data

    def create_model(self, data, sensors_id, y, lat, lon, algorithm=None, params=None, escalat=None,
                         max_time=None, filename='newModel', meteo_data: pd.DataFrame = None, extra_sensors_df=None,
                         look_back=None, lang='ca'):
        """
        Orquestra el cicle complet de creació, entrenament i validació d'un model de forecasting.

        Aquesta funció executa tot el pipeline de Machine Learning: descarrega dades meteorològiques històriques,
        prepara i fusiona datasets, aplica tècniques de finestra temporal (windowing), gestiona col·linearitats
        i valors nuls, escala les dades, selecciona les millors característiques i, finalment, entrena el model
        dividint les dades en conjunts de train, validació i test (60/20/20). Finalment, desa el model i
        les seves mètriques de rendiment.

        :param data: DataFrame original amb les dades del sensor principal.
        :param sensors_id: Identificador del sensor a predir.
        :param y: Nom de la columna objectiu (target).
        :param lat: Latitud per a dades meteorològiques.
        :param lon: Longitud per a dades meteorològiques.
        :param algorithm: Algorisme específic o None per a mode automàtic (AutoML).
        :param params: Paràmetres de l'algorisme o None.
        :param escalat: Mètode d'escalat ('minmax', 'robust', 'standard' o None).
        :param max_time: Temps límit per a la cerca d'hiperparàmetres.
        :param filename: Nom del fitxer on es desarà el model .pkl final.
        :param meteo_data: DataFrame previ de meteo o None per descarregar automàticament.
        :param extra_sensors_df: Diccionari amb dades de sensors addicionals.
        :param look_back: Configuració de la finestra temporal (lags).
        :param lang: Idioma per a les notificacions i informes de mètriques.
        :return: None

        Exemple d'estat final de self.db -> dades guardades:
        {
            "model": <sklearn.model_object>,
            "scaler": <sklearn.scaler_object>,
            "metrics": {
                "mae": float,
                "mse": float,
                "r2": float,
                "validation_score": float
            },
            "algorithm": str,
            "look_back": {-1: [int, int]},
            "sensors_id": str
        }
    """
        
        # Reiniciar mètriques per a aquest model
        self.metrics = ForecastMetrics(debug=self.debug, lang=lang)

        extra_vars = {'variables': ['Dia', 'Hora', 'Mes'], 'festius': ['ES', 'CT']}
        feature_selection = 'Tree'
        colinearity_remove_level = 0.9
        if look_back is None:
            # Per defecte mirar les últimes 24h (1..24) enlloc d'ahir (25..48)
            look_back = {-1: [1, 24]}

        # Descarregar dades meteo si no es proporcionen
        if meteo_data is not None and not data.empty:
            start_date = data['timestamp'].min().strftime("%Y-%m-%d")
            end_date = data['timestamp'].max().strftime("%Y-%m-%d")

            logger.info(f"⛅ Descarregant dades meteo històriques de {start_date} a {end_date}")

            url = (
                f"https://archive-api.open-meteo.com/v1/archive"
                f"?latitude={lat}&longitude={lon}"
                f"&start_date={start_date}&end_date={end_date}"
                f"&hourly=temperature_2m,relativehumidity_2m,dewpoint_2m,apparent_temperature,"
                f"precipitation,rain,weathercode,pressure_msl,surface_pressure,cloudcover,"
                f"cloudcover_low,cloudcover_mid,cloudcover_high,et0_fao_evapotranspiration,"
                f"vapor_pressure_deficit,windspeed_10m,windspeed_100m,winddirection_10m,"
                f"winddirection_100m,windgusts_10m,shortwave_radiation,direct_radiation,"
                f"diffuse_radiation,direct_normal_irradiance,terrestrial_radiation"
            )

            try:
                response = requests.get(url).json()
                hourly = response.get("hourly", {})
                timestamps = pd.to_datetime(hourly["time"])
                meteo_data = pd.DataFrame(hourly)
                meteo_data["timestamp"] = timestamps
                meteo_data.drop(columns=["time"], inplace=True)
            except Exception as e:
                logger.error(f"❌ No s'han pogut descarregar les dades meteo històriques: {e}")
                meteo_data = None

        #PREP PAS 0 - preparar els df de meteo-data i dades extra
        merged_data = self.prepare_dataframes(data, meteo_data, extra_sensors_df)
        
        # Interpolació temporal dels NaNs inicials
        if 'timestamp' in merged_data.columns:
            merged_data.set_index('timestamp', inplace=True)
            merged_data.interpolate(method='time', inplace=True)
            merged_data.reset_index(inplace=True)
            
        merged_data.bfill(inplace=True)
        
        # VALIDACIÓ PAS 0
        self.metrics.validate_dataframe_preparation(data, meteo_data, extra_sensors_df, merged_data)

        if merged_data.empty:
            logger.error(f"\n ************* \n ❌ No hi ha dades per a realitzar el Forecast \n *************")
            return

        # PAS 1 - Fer el Windowing
        dad_before_windowing = merged_data.copy()
        dad = self.do_windowing(merged_data, look_back)
        
        # VALIDACIÓ PAS 1
        self.metrics.validate_windowing(dad_before_windowing, dad, look_back)

        # PAS 2 - Crear variable dia_setmana, hora, més i meteoData
        dad = self.timestamp_to_attrs(dad, extra_vars)
        
        # VALIDACIÓ PAS 2
        self.metrics.validate_temporal_features(dad, extra_vars)

        # PAS 3 - Treure Col·linearitats
        dad_before_colinearity = dad.copy()
        [dad, to_drop] = self.colinearity_remove(dad, y, level=colinearity_remove_level)
        colinearity_remove_level_to_drop = to_drop
        
        # VALIDACIÓ PAS 3
        self.metrics.validate_colinearity_removal(dad_before_colinearity, dad, to_drop, y, colinearity_remove_level)

        # PAS 4 - Gestió de NaN (Interpolació + Eliminació)
        dad.replace([np.inf, -np.inf], np.nan, inplace=True)
        dad_before_nan = dad.copy()
        
        # Interpolació temporal
        X = dad.interpolate(method='time')
        X = X.bfill()
        X = X.dropna()
        
        # VALIDACIÓ PAS 4
        self.metrics.validate_nan_handling(dad_before_nan, X)
        
        # PAS 5 - Desfer el dataset i guardar matrius X i y
        nomy = y
        y = pd.to_numeric(X[nomy], errors='raise')
        
        # VALIDACIÓ CORRELACIÓ (Abans d'eliminar y i fer selecció)
        self.metrics.validate_feature_target_correlation(X, nomy)
        
        del X[nomy]
        
        # Divisió Train/Validation/Test (60/20/20) 

        # PAS 6 - Escalat
        X_before_scaling = X.copy()
        X, scaler = self.scalate_data(X, escalat)
        
        # VALIDACIÓ PAS 6
        self.metrics.validate_scaling(X_before_scaling, X, escalat)

        # PAS 7 - Seleccionar atributs
        [model_select, X_new, y_new] = self.get_attribs(X, y, feature_selection)
        
        # VALIDACIÓ PAS 7
        X_before_selection = X if isinstance(X, np.ndarray) else X.values
        self.metrics.validate_feature_selection(X_before_selection, X_new, feature_selection)

        # PAS 8 - Crear el model
        # Dividir les dades en 60% Train, 20% Validation, 20% Test
        train_idx = int(len(X_new) * 0.6)
        val_idx = int(len(X_new) * 0.8) # 60% + 20% = 80%

        # Gestió segons tipus de dades (pandas o numpy)
        if isinstance(X_new, pd.DataFrame):
            X_train = X_new.iloc[:train_idx]
            X_val = X_new.iloc[train_idx:val_idx]
            X_test = X_new.iloc[val_idx:]
        else:
            X_train = X_new[:train_idx]
            X_val = X_new[train_idx:val_idx]
            X_test = X_new[val_idx:]
            
        y_train = y_new[:train_idx]
        y_val = y_new[train_idx:val_idx]
        y_test = y_new[val_idx:]

        training_start = time.time()
        # Entrenem amb X_train (60% només)
        [model, score] = self.Model(X_train, y_train.values, algorithm, params, max_time=max_time)
        training_time = time.time() - training_start
        
        # VALIDACIÓ INTERMÈDIA (20% Validation)
        # Validem la bondat de l'entrenament sobre el conjunt de validació
        try:
            val_score = model.score(X_val, y_val.values)
            logger.info(f"📊 Validation Score: {val_score:.4f}")
        except Exception as e:
            logger.warning(f"⚠️ No s'ha pogut calcular el Validation Score: {e}")

        # VALIDACIÓ FINAL (20% Test - Dades ocultes finals)
        y_pred = model.predict(X_test)
        
        # Passem X_test i y_test per calcular les mètriques reals sobre dades noves
        self.metrics.validate_model_training(X_test, y_test.values, y_pred, algorithm, score, training_time)
        
        # Comparar amb baselines (usant dades de test)
        last_val_value = y_val.iloc[-1] if hasattr(y_val, 'iloc') else y_val[-1]
        self.metrics.compare_with_baseline(y_test.values, y_pred, last_history_value=last_val_value)

        # PAS 9 - Guardar el model i les mètriques
        if algorithm is None:
            self.db['max_time'] = max_time
            self.db['algorithm'] = "AUTO"
        else:
            self.db['params'] = params
            self.db['algorithm'] = algorithm

        if meteo_data is not None:
            self.db['meteo_data'] = meteo_data
            self.db['meteo_data_is_selected'] = True
        else:
            self.db['meteo_data'] = None
            self.db['meteo_data_is_selected'] = False

        self.db['model'] = model
        self.db['scaler'] = scaler
        self.db['scaler_name'] = escalat
        self.db['model_select'] = model_select
        self.db['colinearity_remove_level_to_drop'] = colinearity_remove_level_to_drop
        self.db['extra_vars'] = extra_vars
        self.db['look_back'] = look_back
        self.db['score'] = score
        self.db['objective'] = nomy
        self.db['initial_data'] = data
        self.db['sensors_id'] = sensors_id
        self.db['extra_sensors'] = extra_sensors_df
        self.db['lat'] = lat
        self.db['lon'] = lon
        
        # Guardar mètriques
        self.db['metrics'] = self.metrics.get_summary()
        self.db['train_val_test_split'] = {
            'train_size': len(X_train),
            'val_size': len(X_val),
            'test_size': len(X_test)
        }
        
        if len(X_test) > 0 and val_idx < len(X):
            self.db['test_set_start_timestamp'] = X.index[val_idx]
        else:
            self.db['test_set_start_timestamp'] = X.index[-1] if len(X) > 0 else pd.Timestamp.now()

        self.save_model(filename)

        if self.debug:
            logger.debug('Model guardat! Score: ' + str(score))

    def forecast(self, data, y, model, future_steps=48):
        """
        Genera prediccions futures de manera recursiva i calcula l'ajust sobre dades històriques.

        Aquesta funció implementa un bucle recursiu on cada predicció s'utilitza com a entrada (lag)
        per a la següent hora. Aplica tot el pipeline de transformació (windowing, atributs
        temporals, eliminació de colinearitats, escalat i selecció) a cada iteració. A més,
        calcula la predicció sobre el conjunt de test actual per permetre la comparació visual.

        :param data: DataFrame amb les dades històriques recents (llavor per a la recursivitat).
        :param y: Nom de la variable objectiu a predir.
        :param model: Objecte del model entrenat per realitzar les inferències.
        :param future_steps: Nombre de passos (hores) a predir cap al futur.
        :return: Una tupla amb el DataFrame de prediccions, passades i futures, els valors reals de test i l'ID del sensor.
        (
            pd.DataFrame({"value": [float, ...]}, index=[datetime, ...]),
            pd.Series([float, ...], index=[datetime, ...]),
            str
        )
        """

        # PAS 1 - Obtenir els valors del model
        model_select = self.db.get('model_select', [])
        scaler = self.db['scaler']
        colinearity_remove_level_to_drop = self.db.get('colinearity_remove_level_to_drop', [])
        extra_vars = self.db.get('extra_vars', {})
        look_back = self.db.get('look_back', {-1: [1, 24]})
        
        # Preparem l'històric inicial
        history_df = data.copy()
        if 'timestamp' in history_df.columns:
            history_df['timestamp'] = pd.to_datetime(history_df['timestamp']).dt.tz_localize(None)
            history_df.set_index('timestamp', inplace=True)
            
        # Interpolació temporal inicial per assegurar continuïtat
        history_df.interpolate(method='time', inplace=True)
        history_df.bfill(inplace=True) # Seguretat extra
        
        predictions = []
        future_indexes = []
        
        # Bucle de predicció recursiva
        for i in range(future_steps):
            last_timestamp = history_df.index[-1]
            next_timestamp = last_timestamp + pd.Timedelta(hours=1)
            future_indexes.append(next_timestamp)
            
            # Creem una nova fila (buid) per al següent pas
            new_row = pd.DataFrame(index=[next_timestamp], columns=history_df.columns)
            
            # Omplim amb persistència les variables exògenes
            for col in new_row.columns:
                if col != y: 
                     new_row[col] = history_df[col].iloc[-1]
                else:
                     new_row[col] = np.nan
                     
            # Afegim la nova fila a l'històric de treball (només la cua necessària per velocitat)
            working_window = pd.concat([history_df.tail(200), new_row])
            
            # --- PIPELINE DE PREPARACIÓ ---
            
            # 1. Windowing
            df_windowed = self.do_windowing(working_window, look_back)
            
            # Ens quedem només amb l'última fila
            current_step_df = df_windowed.tail(1).copy()
            
            # 2. Atributs temporals
            current_step_df = self.timestamp_to_attrs(current_step_df, extra_vars)
            
            # 3. Eliminar colinearitats
            if colinearity_remove_level_to_drop:
                existing_cols = [col for col in colinearity_remove_level_to_drop if col in current_step_df.columns]
                current_step_df.drop(existing_cols, axis=1, inplace=True)
                
            # 4. Eliminar variable objectiu 'y'
            if y in current_step_df.columns:
                del current_step_df[y]
                
            # 5. Gestió de NaNs
            current_step_df.bfill(inplace=True)
            current_step_df.fillna(0, inplace=True)
            
            # 6. Escalat
            if scaler:
                try:
                    current_step_df = pd.DataFrame(scaler.transform(current_step_df), index=current_step_df.index, columns=current_step_df.columns)
                except Exception:
                    pass

            # 7. Selecció d'atributs
            if model_select:
                try:
                     current_step_array = model_select.transform(current_step_df.values)
                except:
                     current_step_array = current_step_df.values
            else:
                current_step_array = current_step_df.values

            # --- PREDICCIÓ ---
            try:
                pred_val = float(model.predict(current_step_array)[0])
            except Exception as e:
                logger.error(f"Error en predicció pas {i}: {e}")
                pred_val = 0.0

            predictions.append(pred_val)
            
            # Actualitzem el valor predit a l'històric per a la següent iteració
            new_row[y] = pred_val
            history_df = pd.concat([history_df, new_row])
            
        forecast_output = pd.DataFrame(
            predictions,
            index=future_indexes,
            columns=[y]
        )
        
        # Recalculem el passat en mode batch per al gràfic 'fit'
        df_fit = self.do_windowing(data, look_back)
        df_fit = self.timestamp_to_attrs(df_fit, extra_vars)
        if colinearity_remove_level_to_drop:
             existing_cols = [col for col in colinearity_remove_level_to_drop if col in df_fit.columns]
             df_fit.drop(existing_cols, axis=1, inplace=True)
        if y in df_fit.columns:
            real_values_column = df_fit[y]
            del df_fit[y]
        else:
            real_values_column = pd.Series()
            
        df_fit.bfill(inplace=True)
        df_fit.fillna(0, inplace=True)
        
        if scaler:
             df_fit = pd.DataFrame(scaler.transform(df_fit), index=df_fit.index, columns=df_fit.columns)
        if model_select:
             df_fit = model_select.transform(df_fit.values)
             
        out = pd.DataFrame(model.predict(df_fit), index=real_values_column.index, columns=[y])
        
        test_start = self.db.get('test_set_start_timestamp')
        if test_start is not None:
            out = out[out.index >= test_start]
            real_values_column = real_values_column[real_values_column.index >= test_start]
        
        final_prediction = pd.concat([out, forecast_output])
        
        return final_prediction, real_values_column,  self.db['sensors_id']

    def save_model(self, model_filename):
        """
        Serialitza l'estat actual del model i la seva configuració en un fitxer binari.

        Crea el directori de destinació si no existeix, guarda el diccionari intern 'self.db'
        (que conté el model, escaladors, mètriques i metadades) utilitzant joblib i,
        finalment, buida la memòria temporal de l'objecte per alliberar recursos.

        :param model_filename: Nom del fitxer (sense extensió) on es desarà el model.
        """
        full_path = os.path.join(self.models_filepath,'forecastings/', model_filename + ".pkl")
        os.makedirs(self.models_filepath + 'forecastings', exist_ok=True)

        if os.path.exists(full_path):
            logger.warning(f"El fitxer {full_path} ja existeix. S'eliminarà.")
            os.remove(full_path)

        joblib.dump(self.db, full_path)
        logger.info(f"  💾 Model guardat al fitxer {model_filename}.pkl")

        self.db.clear()

    def load_model(self, model_filename):
        """
        Carrega un model prèviament entrenat i la seva configuració des d'un fitxer físic.

        Restaura el diccionari intern 'self.db' amb tota la informació necessària per realitzar
        prediccions: l'algorisme entrenat, els escaladors, els paràmetres de finestra temporal
        i les metadades dels sensors associats.

        :param model_filename: Nom del fitxer .pkl (incloent l'extensió) a carregar.
        """
        self.db = joblib.load(self.models_filepath + 'forecastings/' + model_filename)
        logger.info(f"  💾 Model carregat del fitxer {model_filename}")
