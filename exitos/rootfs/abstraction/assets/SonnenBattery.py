import logging
from abstraction.AbsEnergyStorage import AbsEnergyStorage

logger = logging.getLogger("exitOS")


class SonnenBattery(AbsEnergyStorage):
    def __init__(self,config, eff, perc):
        super().__init__(config)
        self.name = "SonnenBattery"
        self.efficiency = eff[1]
        self.actual_percentage = perc[1]

        self.control_charge_sensor = config['control_vars']['carregar']['sensor_id'],
        self.control_discharge_sensor = config['control_vars']['descarregar']['sensor_id'],
        self.control_mode_sensor = config['control_vars']['mode_operar']['sensor_id']

    def simula(self, config, horizon, horizon_min):
        logger.error("************** SIMULA ***************")
        kw_carrega = []
        consumption_profile = []
        total_cost = 0
        actual_capacity_kwh = self.max * self.actual_percentage

        for hour in range(horizon-1):
            start_point = hour * horizon_min
            for minute in range(horizon_min):
                current_min_location = start_point + minute
                if config[current_min_location] > 0:
                    actual_capacity_kwh += config[current_min_location] * self.efficiency
                elif config[current_min_location] < 0:
                    actual_capacity_kwh += config[current_min_location]

                cost = 0

                if actual_capacity_kwh > self.max:
                    if current_min_location == 0:
                        config[current_min_location] = self.max - actual_capacity_kwh
                    else:
                        config[current_min_location] = self.max - kw_carrega[current_min_location - 1]

                    cost = actual_capacity_kwh - self.max
                    actual_capacity_kwh = self.max
                elif actual_capacity_kwh < self.max:
                    if current_min_location == 0:
                        config[current_min_location] = self.min - actual_capacity_kwh
                    else:
                        config[current_min_location] = self.min - kw_carrega[current_min_location - 1]

                kw_carrega.append(actual_capacity_kwh)
                consumption_profile.append(config[current_min_location])
                total_cost += cost

        consumption_profile_24h = [0.0] * 24
        for hour in range(len(consumption_profile)):
            consumption_profile_24h[hour] = consumption_profile[hour]

        return_dict = {
            "consumption_profile": consumption_profile_24h,
            "consumed_Kwh": kw_carrega,
            "total_cost": total_cost,
            "schedule": config
        }

        return return_dict



# to_save_data = {
#     "device_name": current_config['device_name'],
#     "device_type": current_config['device_type'],
#     "max_val": current_config['restrictions']['max'],
#     "min_val": current_config['restrictions']['min'],
#     "efficiency_sensor": current_config['extra_vars']['eficiencia']['sensor_id'],
#     "actual_percentage_sensor": current_config['extra_vars']['percentatge_actual']['sensor_id'],
#     "control_charge_sensor": current_config['control_vars']['carregar']['sensor_id'],
#     "control_discharge_sensor": current_config['control_vars']['descarregar']['sensor_id'],
#     "control_mode_sensor": current_config['control_vars']['mode_operar']['sensor_id']
#
# }

