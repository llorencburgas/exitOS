import logging

from abstraction.DeviceRegistry import register_device
from abstraction.AbsConsumer import AbsConsumer

logger = logging.getLogger("exitOS")

@register_device("EVCharger")
class EVCharger(AbsConsumer):

    def __init__(self,config, database):
        super().__init__(config)
        self.database = database

        self.min = 0   # debug only
        self.max = 100 # debug only


        self.min_power = 0
        self.max_power = 7400
        
        self.max_kwh = float(config.get('restrictions', {}).get('max_capacity_kwh', {}).get('value', 50))
        self.efficiency = 0.95 

        self.socket1_state = config["extra_vars"]["estat_socket_1"]["sensor_id"]
        self.socket2_state = config["extra_vars"]["estat_socket_2"]["sensor_id"]

        self.socket1_limit = config["control_vars"]["limit_socket_1"]["sensor_id"]
        self.socket2_limit = config["control_vars"]["limit_socket_2"]["sensor_id"]

        # TODO: Reemplaçar les següents estructures estadístiques mockejades pel Random Forest Predictor
        self.is_home =  [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
        self.current_kwh = 20.0 
        self.target_kwh = 50.0 

    def simula(self, config, horizon, horizon_min):
        consumption_profile = []
        total_cost = 0
        num_intervals = (horizon) * horizon_min
        current_state_kwh = self.current_kwh
        
        for i in range(num_intervals):
            accio_proposada = config[i]
            
            # Limitar als valors de min/max power
            if accio_proposada > self.max_power: accio_proposada = self.max_power
            elif accio_proposada < self.min_power: accio_proposada = self.min_power

            # Testejar disponibilitat (Si el cotxe no hi és force a 0 i penalitzem enviament inutil)
            if self.is_home[i] == 0:
                accio_real = 0
                if accio_proposada > 0:
                    total_cost += accio_proposada * 10
            else:
                accio_real = accio_proposada
                added_kwh = (accio_real / 1000) * self.efficiency
                current_state_kwh += added_kwh

                # Testejar overcharge
                if current_state_kwh > self.max_kwh:
                    total_cost += (current_state_kwh - self.max_kwh) * 50
                    accio_real = 0
                    current_state_kwh = self.max_kwh
            
            consumption_profile.append(accio_real)

            # Predirp Departure i llançar mega penalitzacions si no s'assoleix Target SoC
            # is_departing = False
            # if i < len(self.is_home) - 1:
            #     if self.is_home[i] == 1 and self.is_home[i+1] == 0:
            #         is_departing = True
            # elif i == len(self.is_home) - 1 and self.is_home[i] == 1:
            #     is_departing = True
            #
            # if is_departing:
            #     if current_state_kwh < self.target_kwh:
            #         total_cost += (self.target_kwh - current_state_kwh) * 500

        consumption_profile_24h = [0.0] * 24
        for i in range(min(len(consumption_profile), 24)):
            consumption_profile_24h[i] = consumption_profile[i]

        return_dict = {
            "consumption_profile": consumption_profile_24h,
            "total_cost": total_cost,
            "schedule": consumption_profile
        }
        return return_dict

    def controla(self, config, current_hour):
        return None

    def get_flexibility(self, optimization_data):
        return None