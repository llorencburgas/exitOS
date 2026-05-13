import logging
from datetime import datetime

from abstraction.DeviceRegistry import register_device
from abstraction.AbsEnergyStorage import AbsEnergyStorage

logger = logging.getLogger("exitOS")


@register_device("SonnenBattery")
class SonnenBattery(AbsEnergyStorage):

    def __init__(self,config, database):
        super().__init__(config)

        self.efficiency = database.get_latest_data_from_sensor(config["extra_vars"]["eficiencia"]["sensor_id"])[1] / 100
        self.actual_percentage = database.get_latest_data_from_sensor(config["extra_vars"]["percentatge_actual"]["sensor_id"])[1] / 100

        self.control_charge_sensor = config['control_vars']['carregar']['sensor_id']
        self.control_discharge_sensor = config['control_vars']['descarregar']['sensor_id']
        self.control_mode_sensor = config['control_vars']['mode_operar']['sensor_id']

        self.max_hours_at_max_power = self.max / self.max_power

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
                # logger.warning(f"Nou estat > self.max - - - > {nou_estat} > {self.max}")
                cost_penalitzacio = (nou_estat - self.max) * 10  # Penalitzem l'excés
                accio_real = (self.max - actual_capacity_kwh) / self.efficiency if accio_proposada > 0 else 0
                actual_capacity_kwh = self.max
            elif nou_estat < self.min:
                # logger.info(f"Nou estat < self.min - - - > {nou_estat} > {self.min}")
                cost_penalitzacio = (self.min - nou_estat) * 10  # Penalitzem descarregar massa
                accio_real = self.min - actual_capacity_kwh
                actual_capacity_kwh = self.min
            else:
                # logger.error(f"ELSE - - - > {nou_estat}")
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

        value_to_HA = abs(config[current_hour])

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
        Necessita que 'optimization_data' contingui 'devices_config' i 'timestamps'.
        """
        if self.name not in optimization_data['devices_config']:
             logger.warning(f"Device {self.name} not found in optimization data")
             return None

        timestamps = optimization_data['timestamps']
        Power_list = optimization_data['devices_config'][self.name]
        
        # Reconstrucció del SoC (kWh) basat en el pla
        # Assumim que l'estat inicial és l'actual
        SoC_list = []
        current_soc = self.actual_percentage * self.max
        
        # Eficiència
        eff = self.efficiency

        for p in Power_list:
            # p > 0 -> Carregant (incrementa SoC amb pèrdues)
            # p < 0 -> Descarregant (decrementa SoC)
            
            if p > 0:
                current_soc += p * eff
            else:
                current_soc += p       #(no puc restar a valor negatiu, he de sumar)
            
            if current_soc > self.max: current_soc = self.max
            if current_soc < self.min: current_soc = self.min
            
            SoC_list.append(current_soc)

        # Unificació de longituds
        min_len = min(len(timestamps), len(SoC_list), len(Power_list))
        
        Pc_max = self.max_power # Potència màxima de càrrega
        Pd_max = self.min_power # Potència màxima de descàrrega
        
        fup = []
        fdown = []
        
        def get_soc_contribution(p):
            return p * eff if p > 0 else p
        
        for t in range(min_len):
            original_power = Power_list[t]
            
            # LÍMIT CAP AMUNT (augmentar consum / carregar més)
            max_allowed_delta_up = float('inf')
            for f_t in range(t, min_len):
                allowed = self.max - SoC_list[f_t]
                if allowed < max_allowed_delta_up:
                    max_allowed_delta_up = allowed
                    
            target_soc_up = get_soc_contribution(original_power) + max_allowed_delta_up
            actual_new_power_up = target_soc_up / eff if target_soc_up > 0 else target_soc_up
            
            fup_t = min(Pc_max, actual_new_power_up) - original_power
            if fup_t < 0: fup_t = 0
            
            # LÍMIT CAP A BAIX (reduir consum / descarregar)
            max_allowed_delta_down = float('-inf')
            for f_t in range(t, min_len):
                allowed = self.min - SoC_list[f_t]
                if allowed > max_allowed_delta_down:
                    max_allowed_delta_down = allowed
                    
            target_soc_down = get_soc_contribution(original_power) + max_allowed_delta_down
            actual_new_power_down = target_soc_down / eff if target_soc_down > 0 else target_soc_down
            
            fdown_t = max(Pd_max, actual_new_power_down) - original_power
            if fdown_t > 0: fdown_t = 0
                                       
            fup.append(fup_t)
            fdown.append(fdown_t)
            
        return fup, fdown, Power_list, timestamps[:min_len]

    def initialize_flex_tracker(self, baseline_plan):
        self.flex_plan = list(baseline_plan)
        self.soc_plan = []
        
        current_soc = self.actual_percentage * self.max
        eff = self.efficiency
        
        for p in self.flex_plan:
            if p > 0: current_soc += p * eff
            else: current_soc += p
                
            if current_soc > self.max: current_soc = self.max
            if current_soc < self.min: current_soc = self.min
            
            self.soc_plan.append(current_soc)

    def reserve_flexibility(self, hour, requested_power):
        if requested_power == 0: return 0
        
        eff = self.efficiency
        original_power = self.flex_plan[hour]
        
        # Comprovem els límits de hardware
        new_power = original_power + requested_power
        if new_power > self.max_power:
            new_power = self.max_power
        elif new_power < self.min_power: 
            new_power = self.min_power
            
        actual_req = new_power - original_power
        if actual_req == 0: return 0
        
        # Contribució al canvi del SOC
        def get_soc_contribution(p):
            return p * eff if p > 0 else p
            
        delta_soc = get_soc_contribution(new_power) - get_soc_contribution(original_power)
        
        max_allowed_delta = delta_soc
        
        # Validar si aquest canvi de SOC incompleix cap condició present o futura
        if delta_soc > 0: # Ens apropem al límit màxim (max)
            for t in range(hour, len(self.soc_plan)):
                allowed = self.max - self.soc_plan[t]
                if allowed < max_allowed_delta:
                    max_allowed_delta = allowed
        else: # Ens apropem al límit mínim (min)
            for t in range(hour, len(self.soc_plan)):
                allowed = self.min - self.soc_plan[t] # allowed serà negatiu o 0
                if allowed > max_allowed_delta: # Ens quedem amb el més restrictiu envers a 0
                    max_allowed_delta = allowed
                    
        # Reconvertim la variació permesa del SOC a l'increment de potència actual
        target_soc_contribution = get_soc_contribution(original_power) + max_allowed_delta
        
        if target_soc_contribution > 0:
            actual_new_power = target_soc_contribution / eff
        else:
            actual_new_power = target_soc_contribution
            
        actual_accepted_power = actual_new_power - original_power
        
        # Desem l'estat pel següent dispositiu/hora
        self.flex_plan[hour] = actual_new_power
        for t in range(hour, len(self.soc_plan)):
            self.soc_plan[t] += max_allowed_delta
            
        return actual_accepted_power

