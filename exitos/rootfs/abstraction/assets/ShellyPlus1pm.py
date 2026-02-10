import logging
from datetime import datetime

from abstraction.DeviceRegistry import register_device
from abstraction.AbsConsumer import AbsConsumer

logger = logging.getLogger("exitOS")


@register_device("ShellyPlus1pm")
class ShellyPlus1pm(AbsConsumer):

    def __init__(self,config, database):
        super().__init__(config)
        self.database = database
        self.is_on = None #??
        self.min = 0
        self.max = 1

        self.sensor_name = config["extra_vars"]["consum_interruptor"]["sensor_id"]
        self.consumption = self.get_consumption_when_ON(database.get_data_from_sensor(self.sensor_name))

    def simula(self, config, horizon, horizon_min):
        total_cost = 0
        self.horizon = horizon
        self.horizon_min = horizon_min
        consumption_hourly = []

        for hour in range(self.horizon -1):
            start_point = hour * self.horizon_min
            for minute in range(self.horizon_min):
                current_min_location = start_point + minute

                if config[current_min_location] == 0:
                    consumption_hourly.append(0)
                    cost = 0
                elif config[current_min_location] == 1:
                    consumption_hourly.append(self.consumption)
                    cost = self.consumption

                total_cost += cost

        return_dict = {
            "consumption_profile": consumption_hourly,
            "total_cost": total_cost,
            "schedule": config
        }
        return return_dict

    def controla(self, config,current_hour):
        current_pos = self.vbound_start + current_hour
        logger.info(f"     ▫️ Configurant {self.name} -> {config[current_pos]}")

        current_state = self.database.get_current_sensor_state(self.sensor_name)
        if current_state is None: return None

        if current_state[0] != config[current_pos]:
            return config[current_pos], self.sensor_name, "switch"

    def get_consumption_when_ON(self, data):
        """
        Calcula la mitjana de consum quan l'interruptor està encés. Mira un màxi mde 500 valors
        """
        max_value = max(data['value'])
        treshold = max_value / 2

        counter = 0
        aggregated = 0
        for val in range(len(data['value'])):
            if counter >= 500: continue
            if data['value'][val] > treshold:
                counter += 1
                aggregated += data['value'][val]

        median = round(aggregated / counter, 3)
        return median

    def get_flexibility(self, optimization_data):
        """
        Calcula la flexibilitat del dispositiu Shelly.
        Flexibilitat es basa en si està ON o OFF.
        """
        if self.name not in optimization_data['devices_config']:
            return None
            
        device_result = optimization_data['devices_config'][self.name]
        timestamps = optimization_data['timestamps']
        
        # Shelly retorna 'consumption_profile' (0 o self.consumption) a 'return_dict' de simula
        # A 'save_optimization', devices_config[name] guarda el return_dict.
        
        consumption_profile = device_result['consumption_profile']
        # Schedule (0 o 1)
        schedule = device_result['schedule'] 
        
        min_len = min(len(timestamps), len(consumption_profile))
        
        fup = []
        fdown = []
        
        for t in range(min_len):
            con = consumption_profile[t]
            # Si està ON (consumint), tenim flex_down (podem apagar-lo) -> Potència que deixem de consumir
            # Si està OFF (no consumint), tenim flex_up (podem encendre'l) -> Potència que podem consumir
            
            # Flex Up: Capacitat d'augmentar consum. Si està OFF, podem consumir self.consumption. Si ON, 0.
            if con == 0:
                flex_up = self.consumption
            else:
                flex_up = 0
                
            # Flex Down: Capacitat de reduir consum. Si està ON, podem reduir self.consumption. Si OFF, 0.
            if con > 0:
                flex_down = con
            else:
                flex_down = 0
                
            fup.append(flex_up)
            fdown.append(flex_down)
            
        return fup, fdown, consumption_profile, timestamps[:min_len]

