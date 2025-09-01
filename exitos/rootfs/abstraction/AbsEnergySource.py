# Class that is the parent for all different energy sources

from abc import abstractmethod


class AbsEnergySource:
    """
    Class that is the parent for all different energy sources
    """

    def __init__(self,name):
        # Initialize the energy source with the given configuration and name
        self.name = name
        self.min = None
        self.max = None
        self.acive_hours = None

    @abstractmethod
    def doSimula(self, calendar, **kwargs):
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
