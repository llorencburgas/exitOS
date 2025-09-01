from abc import abstractmethod

class AbsGenerator:
    """
    Class that is the parent for the different energy generators
    """

    def __init__(self, name):
        self.name = name
        self.calendar_range = None
        self.active_hours = None

        self.debug_var = 0

    @abstractmethod
    def doSimula(self, calendar, **kwargs):
        """
        Method to simulate the generator
        :param calendar: the calendar
        :param kwargs: dictionary with all the extra necessary arguments
        :return: None
        """
        pass

    def obtainProductionByHour(self, hour):
        """
        Method to obtain the production of the generator for a given hour
        :param hour: the hour of the day
        :return: the production of the generator for that hour
        """
        # return self.production[hour]
        return self.debug_var

    def obtainProduction(self):
        """
        Method to obtain the production of the generator
        :return: the production of the generator
        """
        # return self.production
        return self.debug_var

    def obtainDailyProduction(self):
        """
        Method to obtain the daily production of the generator
        :return: the daily production of the generator
        """
        # return sum(self.production)
        return self.debug_var