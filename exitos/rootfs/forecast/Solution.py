import abstraction.AbsConsumer as AbsConsumer

class Solution:
    """
    Classe per representnar una possible solució de configuració
    """

    def __init__(self, consumers = {}, generators = {}, energy_sources = {}):

        self.consumers = consumers
        self.generators = generators
        self.energy_sources = energy_sources

        self.consum_hora = []
        self.preu_venta_hora = []
        self.preu_llum_horari = 0
        self.preu_total = 0

        self.timestamps = []
        self.perfil_consum_energy_source = []
        self.capacitat_actual_energy_source = []
        self.generadors = []
        self.consumidors = []


