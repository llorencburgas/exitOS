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

        # self.brand = brand
        # self.max = max
        # self.min = min
        # self.efficiency_sensor = eff
        # self.actual_percentage_sensor = perc
        # self.control_charge_sensor = charge
        # self.control_discharge_sensor = discharge
        # self.control_mode_sensor = mode

    #
    #
    #
    #
    # @abstractmethod
    # def Simula(self, calendar, **kwargs):
    #     """
    #     Method to simulate the energy source
    #     :param calendar: the calendar
    #     :param kwargs: dictionary with all the extra necessary arguments
    #     :return: None
    #     """
    #     pass
    #
    # @abstractmethod
    # def canviaSimula(self, simImpl):
    #     """
    #     Method to change the simulation implementation
    #     :param simImpl: the new simulation implementation
    #     :return: None
    #     """
    #     pass
    #
    # @abstractmethod
    # def resetToInit(self):
    #     """
    #     Method to reset the energy source to its initial state
    #     :return: None
    #     """
    #     pass
