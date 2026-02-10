import logging
from datetime import datetime

from abstraction.DeviceRegistry import register_device
from abstraction.AbsEnergyStorage import AbsEnergyStorage

logger = logging.getLogger("exitOS")


@register_device("SonnenBattery")
class SonnenBattery(AbsEnergyStorage):

    def __init__(self,config, database):
        super().__init__(config)

        self.efficiency = database.get_latest_data_from_sensor(config["extra_vars"]["eficiencia"]["sensor_id"])[1]
        self.actual_percentage = database.get_latest_data_from_sensor(config["extra_vars"]["percentatge_actual"]["sensor_id"])[1]

        self.control_charge_sensor = config['control_vars']['carregar']['sensor_id']
        self.control_discharge_sensor = config['control_vars']['descarregar']['sensor_id']
        self.control_mode_sensor = config['control_vars']['mode_operar']['sensor_id']

    def simula(self, config, horizon, horizon_min):
        kw_carrega = []  # Estat de càrrega (SoC) en cada moment
        consumption_profile = []  # El que realment consumeix/aporta la bateria
        total_cost = 0

        actual_capacity_kwh = self.max * self.actual_percentage
        num_intervals = (horizon - 1) * horizon_min

        for i in range(num_intervals):
            accio_proposada = config[i]

            # Calculem el nou estat teòric
            if accio_proposada > 0:  # Carregant
                nou_estat = actual_capacity_kwh + (accio_proposada * self.efficiency)
            else:  # Descarregant
                nou_estat = actual_capacity_kwh + accio_proposada

            accio_real = accio_proposada
            cost_penalitzacio = 0

            # Control de límits (sense modificar el vector 'config' original)
            if nou_estat > self.max:
                cost_penalitzacio = (nou_estat - self.max) * 10  # Penalitzem l'excés
                accio_real = (self.max - actual_capacity_kwh) / self.efficiency if accio_proposada > 0 else 0
                actual_capacity_kwh = self.max
            elif nou_estat < self.min:
                cost_penalitzacio = (self.min - nou_estat) * 10  # Penalitzem descarregar massa
                accio_real = self.min - actual_capacity_kwh
                actual_capacity_kwh = self.min
            else:
                actual_capacity_kwh = nou_estat

            kw_carrega.append(actual_capacity_kwh)
            consumption_profile.append(accio_real)
            total_cost += cost_penalitzacio


        consumption_profile_24h = [0.0] * 24
        for i in range(min(len(consumption_profile), 23)):
            consumption_profile_24h[i + 1] = consumption_profile[i]

        return_dict = {
            "consumption_profile": consumption_profile_24h,
            "consumed_Kwh": kw_carrega,
            "total_cost": total_cost,
            "schedule": consumption_profile
        }

        return return_dict


    def controla(self, config,current_hour):

        positive_value = abs(config[current_hour])
        value_to_HA = positive_value * 1000

        if config[current_hour] >= 0:
            logger.info(f"     ▫️ Configurant {self.name} -> 🔋 Charge {value_to_HA}")
            return value_to_HA, self.control_charge_sensor, 'number'
        elif config[current_hour] < 0:
            logger.info(f"     ▫️ Configurant {self.name} -> 🪫 Discharge {value_to_HA}")
            return value_to_HA, self.control_discharge_sensor, 'number'

        return None

    def get_flexibility(self, optimization_data):
        """
        Calcula la flexibilitat de la bateria Sonnen.
        Necessita que 'optimization_data' contingui 'SoC', 'Power', 'timestamps'.
        """
        if self.name not in optimization_data['devices_config']:
             logger.warning(f"Device {self.name} not found in optimization data")
             return None


        timestamps = optimization_data['timestamps']
            
        device_result = optimization_data['devices_config'][self.name]
        
        # Mapeig de variables
        SoC_list = device_result['consumed_Kwh'] # Això és kWh acumulats
        Power_list = device_result['schedule'] # Això és kW
        
        # Si la llista de timestamps és diferent de la de dades, igualar-les
        min_len = min(len(timestamps), len(SoC_list), len(Power_list))
        
        SoC_max = self.max
        SoC_min = self.min
        Pc_max = 2.5 # Hauria de venir de config, però el posarem hardcoded com a l'original si no hi és
        Pd_max = 2.5
        eff = 0.95
        # Recuperar eficiència real si la tenim
        # self.efficiency es calcula al init amb sensor, aquí potser millor usar self.efficiency si està disponible o 0.95
        if hasattr(self, 'efficiency') and self.efficiency:
             eff = float(self.efficiency)

        delta_t = 1 # Hora
        
        fup = []
        fdown = []
        
        for t in range(min_len):
            SoC_t = SoC_list[t]
            Pb_t = Power_list[t]
            
            # Flex Up (Carregar més / Reduir descàrrega)
            # max(0, min(Pc_max, (SoC_max - SoC_t)/eff) - Pb_t)
            # Nota: la fórmula original era (SoC_max - SoC_t) / (eff * delta_t) - Pb_t
            
            flex_up = max(0,
                           min(Pc_max,
                                (SoC_max - SoC_t) / (eff * delta_t)) - Pb_t)

            # Flex Down (Descarregar més / Reduir càrrega)
            # max(0, Pb_t + min(Pd_max, (SoC_t - SoC_min))/delta_t)
            
            flex_down = max(0,
                            Pb_t + min(Pd_max,
                                       (SoC_t - SoC_min) / delta_t))
                                       
            fup.append(flex_up)
            fdown.append(flex_down)
            
        return fup, fdown, Power_list, timestamps[:min_len]
