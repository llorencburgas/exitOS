from abc import ABC, abstractmethod


class AbsDevice(ABC):
    def __init__(self,config):
        self.config = config
        self.name = config["device_name"]

        self.vbound_start = 0
        self.vbound_end = 0

    @abstractmethod
    def simula(self, *args, **kwargs):
        pass

    @abstractmethod
    def controla(self, *args, **kwargs):
        pass

