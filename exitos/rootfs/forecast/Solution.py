import abstraction.AbsConsumer as AbsConsumer

class Solution:
    """
    Classe per representnar una possible solució de configuració
    """

    def __init__(self, consumers = {}, generators = {}):

        self.consumers = consumers
        self.generators = generators

        #Inicialitzar atributs per fer seguiment del balanç d'energia, costs i capacitat
        self.balanc_energetic_per_hores = [] # balanç energia per hora
        self.numero_assets_ok = 0            # Counter de successful assets
        self.preu_cost = 9999999999          # placeholder del preu
        self.cost_aproximacio = 0            # Aproximació del cost
        self.temps_tardat = 0                # Delay time

        self.consumption_data = {}           # Consumption tracking
        self.production_data = {}            # Production tracking

        self.model_variables = []            # Variables usades en el model
        self.cost_per_hours = []             # Cost per hora

    def saveConsumersProfileData(self, profile):
        """Saves the consumers profile data"""
        consumer: AbsConsumer

        profile_aux = profile
        for consumer_class in self.consumers:
            for consumer in self.consumers[consumer_class].keys():
                if profile_aux.__contains__(consumer):
                    self.consumption_data[consumer] = profile_aux[consumer]
                    profile_aux.pop(consumer)

    def saveGeneratorsProfileData(self, profile):
        """Saves the generators profile data"""
        for generator in profile:
            self.production_data[generator] = profile[generator]

