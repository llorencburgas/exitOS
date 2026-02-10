from abc import ABC, abstractmethod


class AbsDevice(ABC):
    def __init__(self,config):
        self.config = config
        self.name = config["device_name"]

        self.vbound_start = 0
        self.vbound_end = 0

        self.horizon = 24
        self.horizon_min = 1

    @abstractmethod
    def simula(self, *args, **kwargs):
        pass

    @abstractmethod
    def controla(self, *args, **kwargs):
        pass

    def get_flexibility(self, optimization_data):
        """
        Calcula la flexibilitat del dispositiu basant-se en les dades d'optimització.
        Retorna (flex_up, flex_down, power_data, timestamps) o None si no aplica.
        """
        return None

