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

        self.control_charge_sensor = config['control_vars']['carregar']['sensor_id'],
        self.control_discharge_sensor = config['control_vars']['descarregar']['sensor_id'],
        self.control_mode_sensor = config['control_vars']['mode_operar']['sensor_id']


    def simula(self, config, horizon, horizon_min):
        logger.info(f"Sonnen_Simula -> Self.max = {self.max}")
        logger.info(f"Sonnen_Simula -> Self.actual_percentage = {self.actual_percentage}")

        kw_carrega = []
        consumption_profile = []
        total_cost = 0
        actual_capacity_kwh = self.max * self.actual_percentage
        self.horizon = horizon
        self.horizon_min = horizon_min

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


    def controla(self, config,current_hour):
        for i in range(self.horizon * self.horizon_min):
            if config[i] == current_hour:
                logger.info(f"     ▫️ Configurant {self.name} -> {config[i]}")

                positive_value = abs(config[i])
                if config[i] >= 0:
                    return positive_value, self.control_charge_sensor, 'number'
                elif config[i] < 0:
                    return positive_value, self.control_discharge_sensor, 'number'
        return None