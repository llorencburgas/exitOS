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

