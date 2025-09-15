import logging
import random

logger = logging.getLogger("exitOS")

class Battery:
    def __init__(self, hores_simular:int = 24, minuts = 1, soc_objectiu = None):
        self.perfil_consum = []
        self.capacitat_actual = []

        self.capacitat_maxima = 100 # KWh
        self.capacitat_minima = 0  # KWh
        self.step = 10
        self.capacitat_actual_percentatge = 0.50 # 50%
        self.capacitat_actual_kwh = self.capacitat_actual_percentatge * 100 # kWh
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

    # def __get_soc_objectiu(self, preu_hores):
    #     preu_minim = min(preu_hores)
    #     preu_maxim = max(preu_hores)
    #
    #     intervals = list(range(self.capacitat_maxima, self.capacitat_minima -1, -self.step))
    #     n_intervals = len(intervals)
    #
    #     rang_preus = preu_maxim - preu_minim
    #     amplada_interval = rang_preus / (n_intervals - 1)
    #
    #     soc_objectiu = []
    #
    #     for preu in preu_hores:
    #         index = int((preu - preu_minim) / amplada_interval)
    #         if index >= n_intervals: index = n_intervals - 1
    #         soc_objectiu.append(intervals[index])
    #
    #     self.SOC_objectiu_horari = soc_objectiu
    #     logger.debug(f"Preu de la llum per hores: {preu_hores}")
    #     logger.debug(f"SOC_objectiu (%):          {soc_objectiu}")

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

    def simula(self, soc_objectiu = None):
        """
        Simula el comportament de la bateria al llarg d'un dia a nivell horari.
        """
        if soc_objectiu is None: self.SOC_objectiu_horari = self.__get_soc_objectiu()
        else: self.SOC_objectiu_horari = soc_objectiu

        hores_consum = []
        self.capacitat_actual = []
        self.perfil_consum = []

        for hora in range(self.hores_actives):
            start_point = hora * self.minuts_per_hora
            for minut in range(self.minuts_per_hora):
                self.capacitat_actual.append(self.capacitat_actual_kwh)
                current_minut_location = start_point + minut

                SOC_objectiu_percentatge = self.SOC_objectiu_horari[current_minut_location] / 100
                objectiu_kwh = self.capacitat_maxima * SOC_objectiu_percentatge

                if self.capacitat_actual_kwh < objectiu_kwh: # carregar
                    self.perfil_consum.append((objectiu_kwh - self.capacitat_actual_kwh) * (2 - self.eficiencia))
                elif self.capacitat_actual_kwh > objectiu_kwh: # descarregar
                    self.perfil_consum.append(objectiu_kwh - self.capacitat_actual_kwh)
                else: # inactiu
                    self.perfil_consum.append(0)

                self.capacitat_actual_kwh = objectiu_kwh

                minut_str = self.__get_minut_string(minut)
                hores_consum.append(str(hora) + minut_str)


        perfil_consum_24h = [0.0] * (self.hores_actives * self.minuts_per_hora)
        for hora in range(len(self.perfil_consum)):

            try:
                perfil_consum_24h[hora] = self.perfil_consum[hora]
            except Exception as e:
                logger.info(f"HORA: {hora}  | error: {e}")

        return_dict = {"perfil_consum": perfil_consum_24h,
                       "hora": hores_consum,
                       "capacitat_actual": self.capacitat_actual}
        return return_dict
