# Class that is the parent for all different energy sources
from abstraction.AbsDevice import AbsDevice
from abc import abstractmethod


class AbsEnergyStorage(AbsDevice):
    """
    Class that is the parent for all different energy sources
    """

    def __init__(self, config):
        # Initialize the energy source with the given configuration and name
        super().__init__(config)
        self.min = float(config['restrictions']['min']['value']) # Wh
        self.max = float(config['restrictions']['max']['value']) # Wh
        self.min_power = float(config['restrictions']['potencia_min']['value'])  #W
        self.max_power = float(config['restrictions']['potencia_max']['value'])  #W



