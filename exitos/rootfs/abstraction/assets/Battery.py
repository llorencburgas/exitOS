import logging
import random

logger = logging.getLogger("exitOS")

class Battery:
    def __init__(self, hores_simular:int = 24, minuts = 1, soc_objectiu = None):
        self.perfil_consum = []
        self.capacitat_actual = []

        self.capacitat_maxima = 25 # KWh
        self.capacitat_minima = 0  # KWh
        self.step = 1
        self.capacitat_actual_percentatge = 0.90
        self.capacitat_actual_kwh = self.capacitat_maxima * self.capacitat_actual_percentatge # kWh
        self.eficiencia = 0.95
        self.claus_percentatge = {"100":1, "90": 0.9, "80":0.8, "70":0.7, "60":0.6, "50":0.5, "40":0.4, "30":0.3, "20":0.2, "10":0.1, "0": 0}
        self.hores_actives = hores_simular
        self.minuts_per_hora = minuts

        self.SOC_objectiu_horari = soc_objectiu if soc_objectiu is not None else self.__get_soc_objectiu()

    def __get_soc_objectiu(self):
        soc_objectiu = []
        for i in range(self.hores_actives):
            for j in range(self.minuts_per_hora):
                soc_objectiu.append(random.randint(self.capacitat_minima,self.capacitat_maxima))
        return soc_objectiu

    def __get_minut_string(self, current_time):
        if self.minuts_per_hora == 1:
            return ":00"
        elif self.minuts_per_hora == 2:
            if current_time == 0: return ":00"
            else: return ":30"
        else:
            if current_time == 0: return ":00"
            elif current_time == 1: return ":15"
            elif current_time == 2: return ":30"
            else: return ":45"

    # def simula(self, soc_objectiu = None):
    #     """
    #     Simula el comportament de la bateria al llarg d'un dia a nivell horari. La bateria ha de funcionar amb %
    #     """
    #     if soc_objectiu is None: self.SOC_objectiu_horari = self.__get_soc_objectiu()
    #     else: self.SOC_objectiu_horari = soc_objectiu
    #
    #     hores_consum = []
    #     self.capacitat_actual = []
    #     self.perfil_consum = []
    #
    #     for hora in range(self.hores_actives):
    #         start_point = hora * self.minuts_per_hora
    #         for minut in range(self.minuts_per_hora):
    #             self.capacitat_actual.append(self.capacitat_actual_kwh)
    #             current_minut_location = start_point + minut
    #
    #             SOC_objectiu_percentatge = self.SOC_objectiu_horari[current_minut_location] / 100
    #             objectiu_kwh = self.capacitat_maxima * SOC_objectiu_percentatge
    #
    #             if self.capacitat_actual_kwh < objectiu_kwh: # carregar
    #                 self.perfil_consum.append((objectiu_kwh - self.capacitat_actual_kwh) * (2 - self.eficiencia))
    #             elif self.capacitat_actual_kwh > objectiu_kwh: # descarregar
    #                 self.perfil_consum.append(objectiu_kwh - self.capacitat_actual_kwh)
    #             else: # inactiu
    #                 self.perfil_consum.append(0)
    #
    #             self.capacitat_actual_kwh = objectiu_kwh
    #
    #             minut_str = self.__get_minut_string(minut)
    #             hores_consum.append(str(hora) + minut_str)
    #
    #
    #     perfil_consum_24h = [0.0] * (self.hores_actives * self.minuts_per_hora)
    #     for hora in range(len(self.perfil_consum)):
    #
    #         try:
    #             perfil_consum_24h[hora] = self.perfil_consum[hora]
    #         except Exception as e:
    #             logger.info(f"HORA: {hora}  | error: {e}")
    #
    #     return_dict = {"perfil_consum": perfil_consum_24h,
    #                    "hora": hores_consum,
    #                    "capacitat_actual": self.capacitat_actual}
    #     return return_dict

    def simula_kw(self, soc_objectiu = None):
        """
        Realitza la simulació del comportament de la bateria al llarg d'un dia a nivell horari. La bateria ha de funcionar a Kwh
        """
        if soc_objectiu is None: self.SOC_objectiu_horari = self.__get_soc_objectiu()
        else: self.SOC_objectiu_horari = soc_objectiu

        kw_carrega = []
        consumption_profile = []
        cost_total = 0

        for hora in range(self.hores_actives):
            start_point = hora * self.minuts_per_hora
            for minut in range(self.minuts_per_hora):
                current_minut_location = start_point + minut
                if soc_objectiu[current_minut_location] > 0:
                    self.capacitat_actual_kwh += (soc_objectiu[current_minut_location] * self.eficiencia)
                elif soc_objectiu[current_minut_location] < 0:
                    self.capacitat_actual_kwh += soc_objectiu[current_minut_location]

                cost = 0

                if self.capacitat_actual_kwh > self.capacitat_maxima:
                    if current_minut_location == 0:
                        soc_objectiu[current_minut_location] = self.capacitat_maxima - self.capacitat_actual_kwh #actual - anterior
                    else:
                        soc_objectiu[current_minut_location] = self.capacitat_maxima - kw_carrega[current_minut_location -1]

                    cost = self.capacitat_actual_kwh - self.capacitat_maxima
                    self.capacitat_actual_kwh = self.capacitat_maxima

                elif self.capacitat_actual_kwh < self.capacitat_minima:
                    if current_minut_location == 0:
                        soc_objectiu[current_minut_location] = self.capacitat_minima - self.capacitat_actual_kwh
                    else:
                        soc_objectiu[current_minut_location] = self.capacitat_minima - kw_carrega[current_minut_location -1]

                    cost = self.capacitat_minima - self.capacitat_actual_kwh
                    self.capacitat_actual_kwh = self.capacitat_minima

                kw_carrega.append(self.capacitat_actual_kwh)
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
