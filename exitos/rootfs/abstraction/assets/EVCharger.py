import logging

from abstraction.DeviceRegistry import register_device
from abstraction.AbsConsumer import AbsConsumer

logger = logging.getLogger("exitOS")

@register_device("EVCharger")
class EVCharger(AbsConsumer):

    def __init__(self,config, database):
        super().__init__(config)
        self.database = database
        self.min = 0
        self.max = 1

        self.socket1_state = config["extra_vars"]["estat_socket_1"]["sensor_id"]
        self.socket2_state = config["extra_vars"]["estat_socket_2"]["sensor_id"]

        self.socket1_limit = config["control_vars"]["limit_socket_1"]["sensor_id"]
        self.socket2_limit = config["control_vars"]["limit_socket_2"]["sensor_id"]



    def simula(self, config, horizon, horizon_min):
        return_dict = {
            "consumption_profile": [0] * 24,
            "total_cost": 0,
            "schedule": config
        }
        return return_dict

    def controla(self, config, current_hour):
        return None

    def get_flexibility(self, optimization_data):
        return None