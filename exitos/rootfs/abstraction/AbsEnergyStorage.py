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
        self.min = float(config['restrictions']['min']['value'])
        self.max = float(config['restrictions']['max']['value'])



