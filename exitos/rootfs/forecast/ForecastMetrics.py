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
        self.debug = debug
        self.metrics_log = []
        self.step_counter = 0
        self.lang = lang
        self.translations = self.load_locale(lang)

    def load_locale(self, lang):
        """
        Carrega el fitxer d'idioma corresponent
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
        Recupera el text traduït segons la clau (dot notation)
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
        
    def log_step(self, step_name, metrics_dict, level="INFO"):
        """
        Registra les mètriques d'un pas específic
        """
        self.step_counter += 1
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'step_number': self.step_counter,
            'step_name': step_name,
            'metrics': metrics_dict,
            'status': 'OK' if metrics_dict.get('valid', True) else 'WARNING'
        }
        
        self.metrics_log.append(log_entry)
        
        # Log visual per consola
        self._print_step_metrics(step_name, metrics_dict, level)
        
    def _print_step_metrics(self, step_name, metrics, level="INFO"):
        """
        Imprimeix mètriques de forma visual i llegible
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
        Retorna la categoria apropiada segons la mètrica
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
        PAS 0: Validació de la preparació dels DataFrames
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

        self.log_step(self.get_text('step_name.dataframe_preparation'), metrics)
        return metrics
    
    def validate_windowing(self, original_df, windowed_df, look_back):
        """
        PAS 1: Validació del windowing
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
        
        self.log_step(self.get_text('step_name.windowing'), metrics)
        return metrics
    
    def validate_temporal_features(self, df_with_temporal, extra_vars):
        """
        PAS 2: Validació de variables temporals
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
        
        self.log_step(self.get_text('step_name.temporal_features'), metrics)
        return metrics
    
    def validate_colinearity_removal(self, df_before, df_after, removed_cols, y_col, threshold):
        """
        PAS 3: Validació d'eliminació de colinearitats
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
        
        self.log_step(self.get_text('step_name.colinearity_removal'), metrics)
        return metrics
    
    def validate_nan_handling(self, df_before, df_after):
        """
        PAS 4: Validació de gestió de NaN
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
        
        self.log_step(self.get_text('step_name.nan_handling'), metrics)
        return metrics
    
    def validate_scaling(self, df_before, df_after, scaler_name):
        """
        PAS 6: Validació de l'escalat
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
        
        self.log_step(self.get_text('step_name.scaling'), metrics)
        return metrics
    
    def validate_feature_selection(self, X_before, X_after, method):
        """
        PAS 7: Validació de selecció d'atributs
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
        
        self.log_step(self.get_text('step_name.feature_selection'), metrics)
        return metrics
    
    def validate_model_training(self, X, y, y_pred, algorithm, score, training_time, iterations=None):
        """
        PAS 8: Validació de l'entrenament del model
        """
        mae = mean_absolute_error(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        r2 = r2_score(y, y_pred)
        
        # MAPE amb protecció per divisions per zero
        mape = np.mean(np.abs((y - y_pred) / np.where(y != 0, y, 1))) * 100
        
        metrics = {
            'algorithm': algorithm if algorithm else 'AUTO',
            'samples': len(X),
            'features': X.shape[1],
            'mae': round(mae, 4),
            'rmse': round(rmse, 4),
            'r2_score': round(r2, 4),
            'mape': round(mape, 2),
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
        
        if mape > 50:
            logger.warning(f"⚠️  {self.get_text('warnings.high_mape', f'{mape:.2f}')}")
        
        if np.isnan(mae) or np.isnan(rmse):
            metrics['valid'] = False
            logger.error(f"❌ {self.get_text('warnings.nan_metrics')}")
        
        self.log_step(self.get_text('step_name.model_training'), metrics)
        return metrics
    
    def validate_forecast_output(self, forecast_df, original_df, future_steps):
        """
        Validació de les prediccions futures
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
        
        self.log_step(self.get_text('step_name.forecast_validation'), metrics)
        return metrics
    
    def get_summary(self):
        """
        Retorna un resum de totes les mètriques
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
        Exporta les mètriques a un fitxer JSON
        """
        with open(filename, 'w') as f:
            json.dump(self.metrics_log, f, indent=2)
        
        logger.info(f"📊 {self.get_text('summary.exported', filename)}")
        
    def compare_with_baseline(self, y_true, y_pred_model, last_history_value=None):
        """
        Compara el model amb baselines simples
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
        
        self.log_step(self.get_text('step_name.baseline_comparison'), metrics)
        return metrics
