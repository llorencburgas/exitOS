import logging
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from datetime import datetime
import json

logger = logging.getLogger("exitOS")


class ForecastMetrics:
    """
    Sistema de mètriques i validació per al procés de forecasting
    """
    
    def __init__(self, debug=True, lang='ca'):
        """
        Constructor de la classe ForecastMetrics per a la gestió de validacions i informes.

        Inicialitza el sistema de seguiment de mètriques, configurant el mode de depuració,
        el comptador de passos del pipeline i carregant les traduccions corresponents
        per als missatges de validació en l'idioma seleccionat.

        :param debug: Booleà per activar la traçabilitat detallada del procés.
        :param lang: Codi d'idioma ('ca', 'es', 'en') per a les traduccions.
        """
        self.debug = debug
        self.metrics_log = []
        self.step_counter = 0
        self.lang = lang
        self.translations = self.load_locale(lang)

    def load_locale(self, lang):
        """
            Carrega el fitxer de traduccions per als missatges de validació del mòdul de mètriques.

            Busca un fitxer JSON a la carpeta de recursos segons el codi d'idioma proporcionat.
            Si el troba, extreu la secció específica de mètriques; en cas contrari, retorna un
            diccionari buit i manté l'execució amb els valors per defecte.

            :param lang: Codi de l'idioma (ex: 'ca', 'es', 'en') que determina el nom del fitxer.
            :return: Diccionari amb les claus i traduccions de text per a la interfície o informes.
            {
                "step_1_title": str,
                "validation_error": str,
                "metric_label": str
            }
        """
        try:
            # Assumim que la ruta és relativa a on s'executa el server
            with open(f"resources/lang/{lang}.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('forecast_metrics', {})
        except Exception as e:
            logger.warning(f"⚠️ No s'ha pogut carregar l'idioma {lang}: {e}. Usant valors per defecte.")
            return {}

    def get_text(self, key, *args):
        """
        Recupera una cadena de text traduïda a partir d'una clau jeràrquica i hi aplica format.

        Utilitza la notació de punts per navegar pel diccionari de traduccions fins a trobar
        el valor corresponent. Si es proporcionen arguments addicionals, s'injecten en els
        marcadors de posició del text (tipus str.format).

        :param key: Clau de traducció en format de punts (ex: 'errors.nan_found').
        :param args: Valors variables per emplenar els buits del text traduït.
        :return: El text formatat si existeix, o la mateixa clau si no es troba la traducció.
        """
        keys = key.split('.')
        value = self.translations
        
        for k in keys:
            value = value.get(k, None)
            if value is None:
                return key # Retorna la clau si no troba traducció
        
        if args:
            return value.format(*args)
        return value
        
    def log_step(self, step_name, metrics_dict, level="INFO", step_id=None):
        """
        Registra i emmagatzema les mètriques i l'estat d'un pas concret del pipeline.

        Incrementa el comptador de passos, genera un registre amb la marca de temps,
        l'identificador de l'etapa i els indicadors de validesa, i finalment imprimeix
        un resum visual per la consola segons el nivell de log especificat.

        :param step_name: Nom descriptiu del pas executat.
        :param metrics_dict: Diccionari amb els valors numèrics o booleans de control.
        :param level: Nivell de severitat del registre ("INFO", "WARNING", "ERROR").
        :param step_id: Identificador estable utilitzat per a la integració amb el frontend.
        """
        self.step_counter += 1
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'step_number': self.step_counter,
            'step_name': step_name,
            'step_id': step_id,  # Stable ID for frontend
            'metrics': metrics_dict,
            'status': 'OK' if metrics_dict.get('valid', True) else 'WARNING'
        }
        
        self.metrics_log.append(log_entry)
        
        # Log visual per consola
        self._print_step_metrics(step_name, metrics_dict, level)
        
    def _print_step_metrics(self, step_name, metrics, level="INFO"):
        """
        Genera una sortida visual per consola amb el resum detallat de les mètriques d'un pas.

        Dibuixa una capçalera estructurada amb el nom del pas i el seu número d'ordre,
        formata els valors numèrics per a una lectura òptima (control de decimals i milers)
        i etiqueta cada mètrica segons la seva categoria funcional. Finalment, mostra un
        indicador d'estat (èxit o advertència) basat en la validesa del pas.

        :param step_name: Títol o descripció de l'etapa del pipeline que s'està mostrant.
        :param metrics: Diccionari de dades tècniques i indicadors de control.
        :param level: Nivell de log utilitzat per a la impressió (per defecte "INFO").
        """
        separator = "=" * 80
        logger.info(f"\n{separator}")
        logger.info(f"📊 STEP {self.step_counter}: {step_name}")
        logger.info(separator)
        
        for key, value in metrics.items():
            if key == 'valid':
                continue
            
            # Formatació segons el tipus de valor
            if isinstance(value, float):
                if abs(value) < 0.01:
                    formatted_value = f"{value:.6f}"
                else:
                    formatted_value = f"{value:.4f}"
            elif isinstance(value, int):
                formatted_value = f"{value:,}"
            elif isinstance(value, list):
                formatted_value = f"[{len(value)} elements]"
            else:
                formatted_value = str(value)
            
            # Categoria segons la mètrica
            category = self._get_metric_category(key)
            logger.info(f"  {category:<25} ({key}): {formatted_value}")
        
        # Validació del pas
        if metrics.get('valid', True):
            logger.info(f"✅ Status: OK")
        else:
            logger.warning(f"⚠️  Status: WARNING - Revisar aquest pas")
        
        logger.info(separator + "\n")
    
    def _get_metric_category(self, metric_name):
        """
        Classifica una mètrica específica en una categoria funcional per facilitar-ne la lectura.

        Compara el nom de la mètrica amb un mapa de paraules clau predefinit i retorna la
        traducció de la categoria corresponent (com ara 'Files', 'Columnes', 'Mètriques d'error', etc.).
        Si no troba cap coincidència, assigna una categoria genèrica.

        :param metric_name: Nom tècnic de la mètrica que s'ha d'avaluar.
        :return: El nom de la categoria traduït segons el fitxer de localització.
        """
        category_map = {
            'rows': self.get_text('category.rows'),
            'columns': self.get_text('category.columns'),
            'nulls': self.get_text('category.nulls'),
            'duplicates': self.get_text('category.duplicates'),
            'coverage': self.get_text('category.coverage'),
            'features_created': self.get_text('category.features_created'),
            'features_removed': self.get_text('category.features_removed'),
            'correlation_max': self.get_text('category.correlation_max'),
            'mae': self.get_text('category.mae'),
            'rmse': self.get_text('category.rmse'),
            'r2': self.get_text('category.r2'),
            'mape': self.get_text('category.mape'),
            'time': self.get_text('category.time'),
            'reduction': self.get_text('category.reduction'),
            'range': self.get_text('category.range')
        }
        
        for key, category in category_map.items():
            if key in metric_name.lower():
                return category
        return self.get_text('category.metric')
    
    def validate_dataframe_preparation(self, sensor_df, meteo_df, extra_sensors, merged_df):
        """
        Avalua la integritat i la qualitat de les dades després de la fase d'unificació (Pas 0).

        Calcula estadístiques clau sobre el volum de dades (files i columnes), el percentatge de
        valors nuls i la cobertura temporal en dies. Verifica que no s'hagi produït una pèrdua
        excessiva de dades durant el remostreig horari i que la densitat de la informació sigui
        suficient per a l'entrenament del model.

        :param sensor_df: DataFrame original del sensor objectiu.
        :param meteo_df: DataFrame amb les dades meteorològiques utilitzades.
        :param extra_sensors: Diccionari o conjunt de sensors addicionals integrats.
        :param merged_df: DataFrame resultant després de la fusió i el resample.
        :return: Diccionari amb les mètriques de volum, cobertura i el flag de validesa.
        """
        metrics = {
            'sensor_rows': len(sensor_df),
            'meteo_rows': len(meteo_df) if meteo_df is not None else 0,
            'extra_sensors_count': len(extra_sensors) if extra_sensors else 0,
            'merged_rows': len(merged_df),
            'merged_columns': len(merged_df.columns),
            'null_percentage': round(merged_df.isnull().sum().sum() / max((merged_df.shape[0] * merged_df.shape[1]), 1) * 100, 2),
            'temporal_coverage_days': (merged_df['timestamp'].max() - merged_df['timestamp'].min()).days if not merged_df.empty else 0,
            'valid': True
        }
        
        # Validacions
        if metrics['null_percentage'] > 50:
            metrics['valid'] = False
            logger.warning(f"⚠️  {self.get_text('warnings.too_many_nulls', metrics['null_percentage'])}")
        
        # Validació ajustada per suportar resampling (e.g. minuts -> hores)
        # En lloc de mirar rows bruts, mirem si tenim prou files per la cobertura temporal (aprox 24 per dia)
        expected_rows_hourly = metrics['temporal_coverage_days'] * 24
        
        if metrics['merged_rows'] < expected_rows_hourly * 0.7:  # Deixem marge del 30% de missings
             # Només disparem warning si també es perd molt respecte l'original (per si l'original ja era horari)
             if metrics['merged_rows'] < metrics['sensor_rows'] * 0.5:
                metrics['valid'] = False
                logger.warning(f"⚠️  {self.get_text('warnings.data_loss', metrics['merged_rows'], metrics['temporal_coverage_days'])}")

        self.log_step(self.get_text('step_name.dataframe_preparation'), metrics, step_id='dataframe_preparation')
        return metrics
    
    def validate_windowing(self, original_df, windowed_df, look_back):
        """
        Verifica la correcta transformació del dataset després d'aplicar la tècnica de finestra temporal (Pas 1).

        Calcula el nombre de noves característiques (lags) generades i les compara amb el valor
        teòric esperat segons la configuració de 'look_back'. També analitza la quantitat de valors
        nuls (NaN) introduïts per l'efecte de desplaçament de la finestra, especialment a l'inici
        del dataset, per assegurar que no es comprometi la densitat de dades útil.

        :param original_df: DataFrame abans d'expandir les columnes temporals.
        :param windowed_df: DataFrame resultant amb les noves columnes de retard (lags).
        :param look_back: Diccionari de configuració que defineix els intervals de la finestra.
        :return: Diccionari amb les mètriques de característiques creades, nuls introduïts i estat de validesa.
        """
        # Calcular features esperades
        expected_features = 0
        for var_name, window in look_back.items():
            if var_name == -1:
                # Per totes les columnes excepte timestamp
                cols_to_window = len([c for c in original_df.columns if c != 'timestamp'])
                expected_features += cols_to_window * (window[1] - window[0])
            else:
                expected_features += (window[1] - window[0])
        
        original_features = len([c for c in original_df.columns if c != 'timestamp'])
        new_features = len(windowed_df.columns) - original_features
        
        # Calcular NaN introduïts
        nan_introduced = windowed_df.isnull().sum().sum() - original_df.isnull().sum().sum()
        
        metrics = {
            'original_features': original_features,
            'new_features': new_features,
            'expected_features': expected_features,
            'total_features': len(windowed_df.columns),
            'nan_introduced': nan_introduced,
            'nan_percentage': round(nan_introduced / (windowed_df.shape[0] * windowed_df.shape[1]) * 100, 2),
            'window_size': look_back.get(-1, [0, 0]),
            'valid': True
        }
        
        # Validacions
        if abs(new_features - expected_features) > 5:
            metrics['valid'] = False
            logger.warning(f"⚠️  {self.get_text('warnings.features_diff', new_features, expected_features)}")
        
        if metrics['nan_percentage'] > 30:
            logger.warning(f"⚠️  {self.get_text('warnings.windowing_nan', metrics['nan_percentage'])}")
        
        self.log_step(self.get_text('step_name.windowing'), metrics, step_id='windowing')
        return metrics
    
    def validate_temporal_features(self, df_with_temporal, extra_vars):
        """
        Comprova la correcta generació i els rangs de les variables temporals i de calendari (Pas 2).

        Valida que les noves columnes (Dia, Hora, Mes) s'hagin afegit correctament i que els seus
        valors estiguin dins dels rangs lògics (0-6 per a dies, 0-23 per a hores, 1-12 per a mesos).
        Així mateix, analitza la proporció de dies festius detectats per assegurar que la distribució
        és coherent i no presenta anomalies en el calendari aplicat.

        :param df_with_temporal: DataFrame que inclou les noves característiques exògenes.
        :param extra_vars: Configuració que especifica quines variables i festius s'havien de crear.
        :return: Diccionari amb el recompte de característiques afegides, els rangs detectats i l'estat de validesa.
        """
        metrics = {
            'features_added': 0,
            'valid': True
        }
        
        # Validar cada variable temporal
        if 'variables' in extra_vars:
            for var in extra_vars['variables']:
                if var in df_with_temporal.columns:
                    metrics['features_added'] += 1
                    
                    if var == 'Dia':
                        unique_vals = df_with_temporal['Dia'].unique()
                        metrics['dia_range'] = f"[{min(unique_vals)}, {max(unique_vals)}]"
                        if not all(0 <= v <= 6 for v in unique_vals):
                            metrics['valid'] = False
                            logger.warning(f"⚠️  {self.get_text('warnings.invalid_day', unique_vals)}")
                    
                    elif var == 'Hora':
                        unique_vals = df_with_temporal['Hora'].unique()
                        metrics['hora_range'] = f"[{min(unique_vals)}, {max(unique_vals)}]"
                        if not all(0 <= v <= 23 for v in unique_vals):
                            metrics['valid'] = False
                            logger.warning(f"⚠️  {self.get_text('warnings.invalid_hour', unique_vals)}")
                    
                    elif var == 'Mes':
                        unique_vals = df_with_temporal['Mes'].unique()
                        metrics['mes_range'] = f"[{min(unique_vals)}, {max(unique_vals)}]"
                        if not all(1 <= v <= 12 for v in unique_vals):
                            metrics['valid'] = False
                            logger.warning(f"⚠️  {self.get_text('warnings.invalid_month', unique_vals)}")
        
        # Validar festius
        if 'festius' in extra_vars and 'festius' in df_with_temporal.columns:
            festius_count = df_with_temporal['festius'].sum()
            festius_percentage = round(festius_count / len(df_with_temporal) * 100, 2)
            metrics['festius_count'] = festius_count
            metrics['festius_percentage'] = festius_percentage
            
            if festius_percentage > 40 or festius_percentage < 5:
                logger.warning(f"⚠️  {self.get_text('warnings.holiday_percentage', festius_percentage)}")
        
        self.log_step(self.get_text('step_name.temporal_features'), metrics, step_id='temporal_features')
        return metrics
    
    def validate_colinearity_removal(self, df_before, df_after, removed_cols, y_col, threshold):
        """
        Supervisa el procés de filtratge de variables redundants o altament correlacionades (Pas 3).

        Calcula la matriu de correlació restant per assegurar que cap parell de variables superi
        el llindar establert i verifica que la variable objectiu (target) no hagi estat eliminada
        per error. També controla el percentatge de reducció del dataset per evitar una pèrdua
        excessiva d'informació que pugui afectar la capacitat predictiva del model.

        :param df_before: DataFrame previ a l'eliminació de col·linearitats.
        :param df_after: DataFrame resultant amb les variables seleccionades.
        :param removed_cols: Llista de noms de les columnes que han estat descartades.
        :param y_col: Nom de la variable objectiu que s'ha de preservar.
        :param threshold: Llindar de correlació (0 a 1) utilitzat per al filtratge.
        :return: Diccionari amb les mètriques de reducció, correlació màxima restant i estat de validesa.
        """
        # Calcular correlació màxima restant
        corr_matrix = df_after.corr().abs()
        np.fill_diagonal(corr_matrix.values, 0)
        max_corr_remaining = corr_matrix.max().max()
        
        metrics = {
            'features_before': len(df_before.columns),
            'features_after': len(df_after.columns),
            'features_removed': len(removed_cols) if removed_cols else 0,
            'removed_columns': removed_cols if removed_cols else [],
            'threshold': threshold,
            'max_correlation_remaining': round(max_corr_remaining, 4),
            'reduction_percentage': round((len(removed_cols) / len(df_before.columns) * 100) if removed_cols else 0, 2),
            'y_preserved': y_col in df_after.columns,
            'valid': True
        }
        
        # Validacions
        if not metrics['y_preserved']:
            metrics['valid'] = False
            logger.error(f"❌ {self.get_text('warnings.target_removed', y_col)}")
        
        if max_corr_remaining > threshold:
            logger.warning(f"⚠️  {self.get_text('warnings.correlation_remaining', threshold, f'{max_corr_remaining:.4f}')}")
        
        if metrics['reduction_percentage'] > 70:
            logger.warning(f"⚠️  {self.get_text('warnings.too_many_features_removed', metrics['reduction_percentage'])}")
        
        self.log_step(self.get_text('step_name.colinearity_removal'), metrics, step_id='colinearity_removal')
        return metrics
    
    def validate_nan_handling(self, df_before, df_after):
        """
        Verifica l'eficàcia de la neteja de valors nuls i l'impacte en el volum del dataset (Pas 4).

        Compara la quantitat de valors nuls abans i després de l'aplicació de mètodes d'interpolació
        i imputació. Controla estrictament el percentatge de files eliminades durant aquest procés
        per evitar una pèrdua d'informació crítica i assegura que el dataset final estigui
        completament lliure de valors nuls abans d'entrar a la fase d'entrenament.

        :param df_before: DataFrame que conté els valors nuls originals o introduïts pel windowing.
        :param df_after: DataFrame net després de la interpolació i l'eliminació de files incompletes.
        :return: Diccionari amb el recompte de valors nuls eliminats, files perdudes i estat de validesa.
        """
        nan_before = df_before.isnull().sum().sum()
        nan_after = df_after.isnull().sum().sum()
        rows_before = len(df_before)
        rows_after = len(df_after)
        
        metrics = {
            'nan_before': nan_before,
            'nan_after': nan_after,
            'nan_removed': nan_before - nan_after,
            'rows_before': rows_before,
            'rows_after': rows_after,
            'rows_lost': rows_before - rows_after,
            'data_loss_percentage': round((rows_before - rows_after) / rows_before * 100, 2),
            'valid': True
        }
        
        # Validacions
        if metrics['data_loss_percentage'] > 30:
            metrics['valid'] = False
            logger.warning(f"⚠️  {self.get_text('warnings.excessive_data_loss', metrics['data_loss_percentage'])}")
        
        if nan_after > 0:
            metrics['valid'] = False
            logger.warning(f"⚠️  {self.get_text('warnings.remaining_nan', nan_after)}")
        
        self.log_step(self.get_text('step_name.nan_handling'), metrics, step_id='nan_handling')
        return metrics
    
    def validate_scaling(self, df_before, df_after, scaler_name):
        """
        Avalua la correcta normalització de les característiques del dataset (Pas 6).

        Calcula estadístiques descriptives (mitjana, desviació estàndard, mínim i màxim) sobre
        les dades transformades per verificar que el mètode d'escalat s'ha aplicat correctament.
        Per al mètode 'minmax', comprova que els valors estiguin continguts entre 0 i 1, mentre
        que per a l'escalat 'standard' (StandardScaler), valida que la mitjana sigui propera
        a 0 i la desviació estàndard propera a 1.

        :param df_before: DataFrame o array abans de realitzar l'escalat.
        :param df_after: DataFrame o array amb les dades ja transformades.
        :param scaler_name: Nom del mètode utilitzat ('minmax', 'standard', 'robust' o None).
        :return: Diccionari amb les estadístiques de l'escalat, el tipus de transformació i l'estat de validesa.
        """
        metrics = {
            'scaler_type': scaler_name,
            'features_scaled': len(df_after.columns) if isinstance(df_after, pd.DataFrame) else df_after.shape[1],
            'valid': True
        }
        
        if scaler_name:
            # Convertir a array si és DataFrame
            data = df_after.values if isinstance(df_after, pd.DataFrame) else df_after
            
            metrics['mean'] = round(np.mean(data), 6)
            metrics['std'] = round(np.std(data), 6)
            metrics['min'] = round(np.min(data), 6)
            metrics['max'] = round(np.max(data), 6)
            metrics['range'] = f"[{metrics['min']}, {metrics['max']}]"
            
            # Validacions segons el tipus de scaler
            if scaler_name == 'minmax':
                if metrics['min'] < -0.01 or metrics['max'] > 1.01:
                    metrics['valid'] = False
                    logger.warning(f"⚠️  {self.get_text('warnings.minmax_range', metrics['range'])}")
            
            elif scaler_name == 'standard':
                if abs(metrics['mean']) > 0.1:
                    logger.warning(f"⚠️  {self.get_text('warnings.standard_mean', metrics['mean'])}")
                if abs(metrics['std'] - 1.0) > 0.1:
                    logger.warning(f"⚠️  {self.get_text('warnings.standard_std', metrics['std'])}")
        else:
            metrics['status'] = 'No scaling applied'
        
        self.log_step(self.get_text('step_name.scaling'), metrics, step_id='scaling')
        return metrics
    
    def validate_feature_selection(self, X_before, X_after, method):
        """
        Analitza l'eficàcia del procés de selecció d'atributs i el seu impacte en el dataset (Pas 7).

        Compara la quantitat de característiques abans i després de l'aplicació de l'algorisme de
        selecció (com 'Tree' o 'ANOVA'). Verifica que no s'hagi buidat el dataset per complet,
        que s'hagi mantingut un nombre mínim de variables per a la predicció i que la reducció
        no sigui excessivament agressiva, la qual cosa podria indicar una pèrdua de senyal rellevant.

        :param X_before: Matriu de dades d'entrada abans de la selecció.
        :param X_after: Matriu de dades d'entrada amb només els atributs seleccionats.
        :param method: Nom del mètode de selecció utilitzat.
        :return: Diccionari amb el recompte de variables, el percentatge de reducció i l'estat de validesa.
        """
        features_before = X_before.shape[1]
        features_after = X_after.shape[1]
        
        metrics = {
            'method': method if method else 'None',
            'features_before': features_before,
            'features_after': features_after,
            'features_removed': features_before - features_after,
            'reduction_percentage': round((features_before - features_after) / features_before * 100, 2),
            'valid': True
        }
        
        # Validacions
        if features_after == 0:
            metrics['valid'] = False
            logger.error(f"❌ {self.get_text('warnings.no_features')}")
        
        if metrics['reduction_percentage'] > 90:
            logger.warning(f"⚠️  {self.get_text('warnings.high_reduction', metrics['reduction_percentage'])}")
        
        if features_after < 5 and features_before > 20:
            logger.warning(f"⚠️  {self.get_text('warnings.few_features', features_after)}")
        
        self.log_step(self.get_text('step_name.feature_selection'), metrics, step_id='feature_selection')
        return metrics
    
    def validate_model_training(self, X, y, y_pred, algorithm, score, training_time, iterations=None):
        """
        Avalua el rendiment del model entrenat mitjançant el càlcul de mètriques d'error i bondat d'ajust (Pas 8).

        Calcula indicadors clau com el MAE, RMSE i R², així com el MAPE i WAPE per mesurar l'error
        percentual de forma robusta. També analitza el biaix (Bias) per detectar si el model
        tendeix a sobreestimar o infraestimar sistemàticament els valors. Realitza validacions
        crítiques sobre el coeficient de determinació i la magnitud de l'error per garantir
        que el model sigui estadísticament significatiu.

        :param X: Matriu de característiques del conjunt de test.
        :param y: Valors reals (ground truth) del conjunt de test.
        :param y_pred: Valors predits pel model per al mateix conjunt.
        :param algorithm: Nom de l'algorisme utilitzat.
        :param score: Puntuació obtinguda durant la fase d'entrenament/optimització.
        :param training_time: Temps total invertit en l'entrenament en segons.
        :param iterations: Nombre de configuracions provades (en cas d'AutoML).
        :return: Diccionari amb el resum de mètriques d'error, temps d'execució i estat de validesa.
        """
        mae = mean_absolute_error(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        r2 = r2_score(y, y_pred)
        
        # MAPE amb protecció per divisions per zero
        mape = np.mean(np.abs((y - y_pred) / np.where(y != 0, y, 1))) * 100
        
        # WAPE (Weighted Absolute Percentage Error) - més robust que MAPE
        total_abs_error = np.sum(np.abs(y - y_pred))
        total_actual = np.sum(np.abs(y))
        wape = (total_abs_error / total_actual * 100) if total_actual > 0 else 0
        
        # BIAS (Mean Error) - Indica si sobreestimem o infraestimem
        bias = np.mean(y_pred - y)
        
        metrics = {
            'algorithm': algorithm if algorithm else 'AUTO',
            'samples': len(X),
            'features': X.shape[1],
            'mae': round(mae, 4),
            'rmse': round(rmse, 4),
            'r2_score': round(r2, 4),
            'mape': round(mape, 2),
            'wape': round(wape, 2),
            'bias': round(bias, 4),
            'training_time_seconds': round(training_time, 2),
            'iterations_tested': iterations if iterations else 'N/A',
            'valid': True
        }
        
        # Validacions
        if r2 < 0:
            metrics['valid'] = False
            logger.warning(f"⚠️  {self.get_text('warnings.negative_r2')}")
        
        if r2 < 0.3:
            logger.warning(f"⚠️  {self.get_text('warnings.low_r2', f'{r2:.4f}')}")
        
        if wape > 50:
            logger.warning(f"⚠️  {self.get_text('warnings.high_wape', f'{wape:.2f}')}")
            
        if abs(bias) > (np.mean(y) * 0.2) if len(y) > 0 and np.mean(y) != 0 else False:
             logger.warning(f"⚠️ Alta desviació sistemàtica (Bias): {bias:.2f}")
        
        if np.isnan(mae) or np.isnan(rmse):
            metrics['valid'] = False
            logger.error(f"❌ {self.get_text('warnings.nan_metrics')}")
        
        self.log_step(self.get_text('step_name.model_training'), metrics, step_id='model_training')
        return metrics

    def validate_feature_target_correlation(self, df, y_col):
        """
        Analitza el poder predictiu de les variables independents respecte a la variable objectiu.

        Calcula el coeficient de correlació de Pearson per a cada columna del dataset en relació
        amb el target. Identifica les 10 característiques amb més influència i verifica si existeix
        un llindar mínim de senyal (0.1) per garantir que el model tingui una base estadística
        sòlida sobre la qual aprendre. Si la correlació màxima és massa baixa, emet una advertència
        sobre la probable falta de capacitat predictiva del futur model.

        :param df: DataFrame que conté tant les característiques com la variable objectiu.
        :param y_col: Nom de la columna que es vol predir (target).
        :return: Diccionari amb la correlació màxima, les variables més rellevants i l'estat de validesa.
        """
        if df.empty or y_col not in df.columns:
            return {'valid': False}
            
        correlations = df.corr()[y_col].abs().sort_values(ascending=False)
        # Treiem el propi target
        correlations = correlations.drop(labels=[y_col], errors='ignore')
        
        top_correlations = correlations.head(10).to_dict()
        max_corr = correlations.max()
        
        metrics = {
            'max_correlation': round(max_corr, 4),
            'top_features': top_correlations,
            'features_above_01': len(correlations[correlations > 0.1]),
            'valid': True
        }
        
        if max_corr < 0.1:
            metrics['valid'] = False
            logger.warning(f"⚠️ Molt baixa correlació detectada (Max: {max_corr:.4f}). El model probablement fallarà.")
            
        self.log_step("Correlació Features-Target", metrics, step_id='feature_correlation')
        return metrics
    
    def validate_forecast_output(self, forecast_df, original_df, future_steps):
        """
        Verifica la coherència i la qualitat de les prediccions generades pel model.

        Comprova que el nombre de passos predits coincideixi amb l'horitzó de previsió sol·licitat
        i analitza la distribució estadística dels valors resultants en comparació amb les dades
        originals. Detecta possibles valors atípics (outliers) que s'allunyin més de tres desviacions
        estàndard de la mitjana històrica i assegura l'absència de valors nuls en la sortida final.

        :param forecast_df: DataFrame que conté els valors predits pel model.
        :param original_df: Sèrie o DataFrame amb les dades històriques de referència.
        :param future_steps: Nombre de passos (horitzó temporal) que s'esperava predir.
        :return: Diccionari amb estadístiques de la predicció, recompte d'outliers i estat de validesa.
            """
        metrics = {
            'forecast_rows': len(forecast_df),
            'expected_rows': future_steps,
            'original_data_rows': len(original_df),
            'forecast_mean': round(forecast_df.iloc[:, 0].mean(), 4),
            'forecast_std': round(forecast_df.iloc[:, 0].std(), 4),
            'forecast_min': round(forecast_df.iloc[:, 0].min(), 4),
            'forecast_max': round(forecast_df.iloc[:, 0].max(), 4),
            'valid': True
        }
        
        # Detectar outliers en prediccions
        original_mean = original_df.mean()
        original_std = original_df.std()
        
        # Prediccions fora de 3 desviacions estàndard
        outliers = forecast_df[
            (forecast_df.iloc[:, 0] < original_mean - 3 * original_std) |
            (forecast_df.iloc[:, 0] > original_mean + 3 * original_std)
        ]
        
        metrics['outliers_count'] = len(outliers)
        metrics['outliers_percentage'] = round(len(outliers) / len(forecast_df) * 100, 2)
        
        # Validacions
        if len(forecast_df) != future_steps:
            metrics['valid'] = False
            logger.warning(f"⚠️  {self.get_text('warnings.forecast_rows_mismatch', len(forecast_df), future_steps)}")
        
        if metrics['outliers_percentage'] > 10:
            logger.warning(f"⚠️  {self.get_text('warnings.forecast_outliers', metrics['outliers_percentage'])}")
        
        if forecast_df.isnull().sum().sum() > 0:
            metrics['valid'] = False
            logger.error(f"❌ {self.get_text('warnings.forecast_nan')}")
        
        self.log_step(self.get_text('step_name.forecast_validation'), metrics, step_id='forecast_validation')
        return metrics
    
    def get_summary(self):
        """
        Genera un informe consolidat de totes les validacions realitzades durant l'execució.

        Calcula estadístiques globals com el percentatge d'èxit del pipeline, el recompte total de
        passos completats i el nombre d'advertències detectades. A més, imprimeix un resum
        executiu per consola i retorna l'historial complet de mètriques emmagatzemades al log
        per a la seva posterior anàlisi o visualització.

        :return: Diccionari amb el resum estadístic de l'execució i el llistat detallat de cada pas.
        """
        total_steps = len(self.metrics_log)
        valid_steps = sum(1 for log in self.metrics_log if log['status'] == 'OK')
        
        summary = {
            'total_steps': total_steps,
            'valid_steps': valid_steps,
            'warning_steps': total_steps - valid_steps,
            'success_rate': round(valid_steps / total_steps * 100, 2) if total_steps > 0 else 0,
            'steps': self.metrics_log
        }
        
        logger.info("\n" + "=" * 80)
        logger.info(self.get_text('summary.title'))
        logger.info("=" * 80)
        logger.info(f"  ✅ {self.get_text('summary.steps_completed', valid_steps, total_steps)}")
        logger.info(f"  ⚠️  {self.get_text('summary.warnings_count', total_steps - valid_steps)}")
        logger.info(f"  🎯 {self.get_text('summary.success_rate', summary['success_rate'])}")
        logger.info("=" * 80 + "\n")
        
        return summary
    
    def export_metrics(self, filename="metrics_log.json"):
        """
        Persisteix l'historial complet de mètriques i validacions en un fitxer de dades extern.

        Escriu el contingut de l'atribut 'metrics_log' en format JSON amb sagnat per facilitar-ne
        la lectura humana. Un cop finalitzada l'escriptura, notifica la ubicació del fitxer
        generat a través del logger.

        :param filename: Nom o ruta del fitxer on s'emmagatzemaran les dades (per defecte "metrics_log.json").
        """
        with open(filename, 'w') as f:
            json.dump(self.metrics_log, f, indent=2)
        
        logger.info(f"📊 {self.get_text('summary.exported', filename)}")
        
    def compare_with_baseline(self, y_true, y_pred_model, last_history_value=None):
        """
        Compara el rendiment del model entrenat respecte a models de referència (baselines) simplificats.

        Calcula l'error (MAE) de dos mètodes base: la persistència (utilitzar l'últim valor conegut
        com a predicció) i la mitjana mòbil. Determina el percentatge de millora del model
        respecte a aquests mètodes i valida si el model és realment útil; si el model no
        supera els baselines simples, es considera que no està aportant valor predictiu real.

        :param y_true: Valors reals del conjunt de dades.
        :param y_pred_model: Valors predits pel model d'aprenentatge automàtic.
        :param last_history_value: Últim valor real conegut abans del set de test per al càlcul de persistència.
        :return: Diccionari amb els MAE de cada mètode, els percentatges de millora i l'estat de validesa.
        """
        # Baseline 1: Persistència (últim valor conegut)
        y_pred_persistence = np.roll(y_true, 1)
        
        if last_history_value is not None:
             # Si tenim l'últim valor histori, el fem servir per la primera predicció
             y_pred_persistence[0] = last_history_value
        else:
             # Si no, fem "trampa" i usem el valor real (error 0)
             y_pred_persistence[0] = y_true[0]
        
        # Baseline 2: Mitjana mòbil
        window = min(24, len(y_true) // 4)
        y_pred_ma = pd.Series(y_true).rolling(window=window, min_periods=1).mean().values
        
        # Calcular mètriques
        mae_model = mean_absolute_error(y_true, y_pred_model)
        mae_persistence = mean_absolute_error(y_true, y_pred_persistence)
        mae_ma = mean_absolute_error(y_true, y_pred_ma)
        
        metrics = {
            'model_mae': round(mae_model, 4),
            'persistence_mae': round(mae_persistence, 4),
            'moving_average_mae': round(mae_ma, 4),
            'improvement_vs_persistence': round((mae_persistence - mae_model) / mae_persistence * 100, 2),
            'improvement_vs_ma': round((mae_ma - mae_model) / mae_ma * 100, 2),
            'valid': mae_model < mae_persistence and mae_model < mae_ma
        }
        
        if not metrics['valid']:
            logger.warning(f"⚠️  {self.get_text('warnings.baseline_fail')}")
        else:
            logger.info(f"✅ {self.get_text('warnings.baseline_improvement_persistence', metrics['improvement_vs_persistence'])}")
            logger.info(f"✅ {self.get_text('warnings.baseline_improvement_ma', metrics['improvement_vs_ma'])}")
        
        self.log_step(self.get_text('step_name.baseline_comparison'), metrics, step_id='baseline_comparison')
        return metrics