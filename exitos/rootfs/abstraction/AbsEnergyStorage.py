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
        self.physical_max = float(config['restrictions']['max']['value']) # Wh
        self.min_power = float(config['restrictions']['potencia_min']['value'])  #W
        self.max_power = float(config['restrictions']['potencia_max']['value'])  #W

        if 'soc_range' in config['restrictions']:
            soc_val = config['restrictions']['soc_range']['value']
            if isinstance(soc_val, list):
                min_pct, max_pct = float(soc_val[0]), float(soc_val[1])
            else:
                parts = str(soc_val).split(',')
                min_pct, max_pct = float(parts[0]), float(parts[1])
            self.min = self.physical_max * (min_pct / 100.0)
            self.max = self.physical_max * (max_pct / 100.0)
        else:
            self.min = float(config['restrictions'].get('min', {}).get('value', 0)) # Wh
            self.max = self.physical_max # Wh



