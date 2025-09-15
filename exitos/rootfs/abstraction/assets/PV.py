import logging

logger = logging.getLogger("exitOS")

class PV:
    def __init__(self, hourly_radiation):
        self.max_output = 2500
        self.min_output = 0
        self.eficiencia = 0.97

        self.numero_plaques = 10
        self.superficie_placa = 1.7
        self.superficie_total = self.numero_plaques * self.superficie_placa



    def get_generacio_horaria(self, hourly_radiation):
        generacio_horaria_total = []
        for hour in hourly_radiation:
            calcul_aux = (hour * self.superficie_total * self.eficiencia) /1000 # Kw
            generacio_hora = min(calcul_aux, self.max_output)
            generacio_horaria_total.append(round(generacio_hora,2))

        return generacio_horaria_total