# Class that is the parent for all different energy sources

from abc import abstractmethod


class AbsEnergyStorage:
    """
    Class that is the parent for all different energy sources
    """

    def __init__(self, config):
        # Initialize the energy source with the given configuration and name
        self.name = config['device_name']
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


        self.vbound_start = 0
        self.vbound_end = 0


    @abstractmethod
    def Simula(self, calendar, **kwargs):
        """
        Method to simulate the energy source
        :param calendar: the calendar
        :param kwargs: dictionary with all the extra necessary arguments
        :return: None
        """
        pass

    @abstractmethod
    def canviaSimula(self, simImpl):
        """
        Method to change the simulation implementation
        :param simImpl: the new simulation implementation
        :return: None
        """
        pass

    @abstractmethod
    def resetToInit(self):
        """
        Method to reset the energy source to its initial state
        :return: None
        """
        pass
