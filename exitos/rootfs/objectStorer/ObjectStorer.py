# -*- coding: utf-8 -*-
import numpy as np
import h5py as h5
import dill
from configparser import ConfigParser


class ObjectStorer:
    """
    Classe que guarda objectes de python binaritzats en dill(pikle extes per permetre mes tipus) en un fitxer hdf5 
    No es pot tenir mes de 1 instancia d'aquest objecte!! Ja que treballa sobre fitxers.
    """
    
    """
    Constants
    """
    import pathlib
    current_dir = pathlib.Path(__file__).parent
    print(current_dir)  # TODO: treure quan verifiqui el funcionament correcte al servidor

    confi = ConfigParser()
    inifile = current_dir / 'config.ini'  # ha de ser així perquè el llegeixi des del WS
    confi.read(inifile)
    
    # nom del fitxer on es guarden els objectes. To do que es carregui des de un .conf
    _file = confi.get('config', 'file')  # 'models.hdf5'

    """
    Constructors, destructors i altres relacionats amb l'objecte
    """

    def __init__(self, debug=False, username='__None__', project_path=None, current_project=None, filename=None):
        """Constructor de l'objecte, Obrim/Creem el fitxer on es desaran les dades"""
        if filename is None:
            filename = username

        # self._file = filename + '.hdf5'
        self._file = 'static/mySuperFile.hdf5'

        if project_path:
            self._file = project_path / 'models' / current_project / self._file
        # grup = username

        "obrim el fitxer i el deixem obert a la variable privada _store"
        self._store = h5.File(self._file, 'a')
        self.user_id = username
        self.debug = debug

        "si no hi ha el grup <grup> el creem"
        # if not self.exist_grup(grup):
        #     self._store.create_group(grup)
        
        if self.debug:
            print('Fitxer linkat')
    
    def __del__(self):
        """destructor de la classe"""
        self._store.close()
        if self.debug:
            print('Fitxer alliberat')
        
    def close(self):
        """destructor de la classe"""
        self._store.close()
        if self.debug:
            print('Fitxer alliberat')

    """
         operacions sobre de grups       
    """    
    def create_grup(self, grup):
        """
        Creen un nou grup de objectes.
        
        grup  --  El nom del nou grup, es un string
        """
        
        "si no hi ha el grup demanat el creem"
        if self.exist_grup(grup):
            print('ERROR - Estas creant un grup de objectes (usuari) existent!!')
        
        #To do -  Comprovar si hi ha caracters estranys als strings [/...]
      
        self._store.create_group(grup)
        
    def delete_grup(self, grup):
        """
        Eliminem un dels grups d'objectes que teniem.
        :parameter grup:  El nom del grup que volem eliminar
        :return: None
        """
        
        "si no hi ha el grup demanat tornem error"
        if not self.exist_grup(grup):
            print("ERROR - Estas eliminant un grup de objectes (usuari) inexistent!!")
                
        #To do -  Comprovar si hi ha caracters estranys als strings [/...]
        
        del self._store[grup]
        
    def get_grups(self):
        """
        Retorna el nom de tots els grups que tenim a l'objecte.
        
        retorna una llista amb l'sring de tots els noms
        """
        return [key for key in self._store.keys()]
    
    def exist_grup(self, grup):  # TODO: grup ara redundant, i grup ja es crea dins el constructor (potser utilitzar create_grup?)
        """
        :parameter grup: -- el nom del grup en string
        :return: true si existeix el grup o false si no existeix.
        """
                
        #To do -  Comprovar si hi ha caracters estranys als strings [/...]
        return grup in [key for key in self._store.keys()]
    
    
    """
    Operacions sobre Objectes
    """   

    def store(self, objecte, nom, grup=None):
        """Guarda un objecte. 
        objecte -- es un objecte python que volem guardar
        nom -- es un string [a zA Z0 9] que l'identifica i permetra recuperar-lo
        grup -- L'string del grup on se guardara l'objecte
        
        """
        if not grup:
            grup = self.user_id
        "si no hi ha el grup demanat el creem automaticament per evitar errors"
        if not self.exist_grup(grup):
            self._store.create_group(grup)
        
        # TODO - Comprovar si existeix l'objecte. -- Maxacar l'existent // Error // no fer res??
                
        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]
        
        self._store[grup].create_dataset(nom, data=np.void(dill.dumps(objecte)))

    def store_info(self, objecte, nom, grup=None):
        """Guarda un objecte.
        objecte -- es un objecte python que volem guardar
        nom -- es un string [a zA Z0 9] que l'identifica i permetra recuperar-lo
        grup -- L'string del grup on se guardara l'objecte

        """
        if not grup:
            grup = self.user_id
        "si no hi ha el grup demanat el creem automaticament per evitar errors"
        if not self.exist_grup(grup):
            self._store.create_group(grup)

        # TODO - Comprovar si existeix l'objecte. -- Maxacar l'existent // Error // no fer res??

        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]

        self._store[grup].create_dataset(nom, data=objecte)

    def get(self, nom, grup=None):
        """
        Recuperem un objecte previament guardat.
        grup/user_id -- es un string que identifica el grup on esta guardat l'objecte
        nom -- es un string que l'identifica l'obj
        """
        if not grup:
            grup = self.user_id

        "si no hi ha el grup demanat el creem"  # TODO: el creem o no retornem res? es tractaria d'un error o no?
        if not self.exist_grup(grup):
            return None

        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]
        
        return dill.loads(self._store[grup][nom][()])

    def get_info(self, nom, grup=None):
        """
        Recuperem un objecte previament guardat.
        grup/user_id -- es un string que identifica el grup on esta guardat l'objecte
        nom -- es un string que l'identifica l'obj
        """

        if not self.exist_grup(grup):
            return None

        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]
        a=self._store[grup][nom][()]
        a=a.decode()

        return a

    def get_stored_names(self, grup=None):
        """
        Retorna els noms de tots els objectes guardats a grup/user_id.
        """
        if not grup:
            grup = self.user_id

        "si no hi ha el grup demanat el creem"
        if not self.exist_grup(grup):
            self._store.create_group(grup)

        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]
        
        return [key for key in self._store[grup].keys()]
    
    def exist_name(self, nom, grup=None):
        """
        Retorna True si existeix un nom a un grup i False si no
        Si el grup/user_id no existeix, retorna False
        """
        if not grup:
            grup = self.user_id

        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]
        
        if self.exist_grup(grup):
            return nom in [key for key in self._store[grup].keys()]
        else:
            return False

    def delete_stored_obj(self, nom, grup=None):
        """
        Elimina un objecte previament guardat al grup/user_id
        """
        if not grup:
            grup = self.user_id

        "si no hi ha el grup demanat el creem"
        if not self.exist_grup(grup): #Cal??? potser no ...
            self._store.create_group(grup)
                        
        # TODO -  Comprovar si hi ha caracters estranys als strings [/...]
        
        del self._store[grup][nom]
