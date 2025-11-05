import logging
import random

logger = logging.getLogger("exitOS")

class Battery:
    def __init__(self, hours_to_simulate:int = 24, minutes_per_hour = 1, max_capacity = 1000,
                 min_capacity = 0, actual_percentage = 0, efficiency = 100):
        """
        :param hours_to_simulate: Hores que es vol simular el programa. Per defecte són 24
        :param minutes_per_hour: Quantitat minutal de la simulació ( 1 = cada hora, 2 = 30 minuts, 3 = 15 minuts)
        :param max_capacity: Capacitat màxima en KwH de la bateria
        :param min_capacity: Capacitat mínima en KwH de la bateria
        :param actual_percentage: Percentatge actual de la bateria (0-1)
        :param efficiency: Eficiencia de la bateria. (0-1) (Battery Health)
        """
        self.perfil_consum = []
        self.capacitat_actual = []

        self.max_capacity = max_capacity # KWh
        self.min_capacity = min_capacity  # KWh
        # self.step = 1
        self.actual_capacity_percentage = actual_percentage
        self.efficiency = efficiency

        self.active_hours = hours_to_simulate
        self.minutes_per_hour = minutes_per_hour

        self.actual_capacity_kwh = self.max_capacity * self.actual_capacity_percentage # kWh
        self.SOC_hourly_objective = [self.max_capacity] * (hours_to_simulate * minutes_per_hour)

    def __get_soc_objectiu(self):
        soc_objectiu = []
        for i in range(self.active_hours):
            for j in range(self.minutes_per_hour):
                soc_objectiu.append(random.randint(self.min_capacity, self.max_capacity))
        return soc_objectiu

    def __get_minut_string(self, current_time):
        if self.minutes_per_hour == 1:
            return ":00"
        elif self.minutes_per_hour == 2:
            if current_time == 0: return ":00"
            else: return ":30"
        else:
            if current_time == 0: return ":00"
            elif current_time == 1: return ":15"
            elif current_time == 2: return ":30"
            else: return ":45"

    def simula_kw(self, soc_objectiu = None):
        """
        Realitza la simulació del comportament de la bateria al llarg d'un dia a nivell horari. La bateria ha de funcionar a Kwh
        """
        if soc_objectiu is None: self.SOC_hourly_objective = self.__get_soc_objectiu()
        else: self.SOC_hourly_objective = soc_objectiu

        kw_carrega = []
        consumption_profile = []
        cost_total = 0

        for hora in range(self.active_hours):
            start_point = hora * self.minutes_per_hour
            for minut in range(self.minutes_per_hour):
                current_minut_location = start_point + minut
                if soc_objectiu[current_minut_location] > 0:
                    self.actual_capacity_kwh += (soc_objectiu[current_minut_location] * self.efficiency)
                elif soc_objectiu[current_minut_location] < 0:
                    self.actual_capacity_kwh += soc_objectiu[current_minut_location]

                cost = 0

                if self.actual_capacity_kwh > self.max_capacity:
                    if current_minut_location == 0:
                        soc_objectiu[current_minut_location] = self.max_capacity - self.actual_capacity_kwh #actual - anterior
                    else:
                        soc_objectiu[current_minut_location] = self.max_capacity - kw_carrega[current_minut_location - 1]

                    cost = self.actual_capacity_kwh - self.max_capacity
                    self.actual_capacity_kwh = self.max_capacity

                elif self.actual_capacity_kwh < self.min_capacity:
                    if current_minut_location == 0:
                        soc_objectiu[current_minut_location] = self.min_capacity - self.actual_capacity_kwh
                    else:
                        soc_objectiu[current_minut_location] = self.min_capacity - kw_carrega[current_minut_location - 1]

                    cost = self.min_capacity - self.actual_capacity_kwh
                    self.actual_capacity_kwh = self.min_capacity

                kw_carrega.append(self.actual_capacity_kwh)
                consumption_profile.append(soc_objectiu[current_minut_location])
                cost_total += cost

        consumption_profile_24h = [0.0] * 24
        for hour in range(len(consumption_profile)):
            consumption_profile_24h[hour] = consumption_profile[hour]

        return_dictionary = {'consumption_profile' : consumption_profile_24h,
                             'consumed_Kwh': kw_carrega,
                             'cost_aproximacio': cost_total,
                             'soc_objectiu': soc_objectiu
                             }

        return return_dictionary
