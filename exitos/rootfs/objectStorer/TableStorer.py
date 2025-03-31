# -*- coding: utf-8 -*-
import pandas as pd


class TableStorer:

    def __init__(self, project=None, username='__None__', filename=None):
        """Constructor de l'objecte, Obrim/Creem el fitxer on es desaran les dades"""
        "obrim el fitxer i el deixem obert a la variable privada _store"
        if project:
            self._store = pd.HDFStore(project + '_' + username + '.h5')
        elif filename:
            self._store = pd.HDFStore(filename)
        # else:
        #     grup = username
        #     self._store = h5.File(self._file, 'a')
        #
        # self.user_id = username

    def get_table(self, table):
        tau1 = self._store.get(table)
        return tau1

    def get_selection(self, table, start, stop):
        tau1 = self._store.select(table, where=['index>="' + start + '" & index<"' + stop + '"'])
        return tau1

    def get_grups(self):
        """
        Retorna una llista amb l'string de tots els noms que tenim al fitxer.
        """
        return [key for key in self._store.keys()]

    def store_table(self, table, data, tz='Europe/Madrid'):
        """
        tz: li hem de dir la zona en que està l'índex ja que ho grava tot com si fos UTC
        """
        # Recuperem lo ultim guardat per no tenir dades duplicades
        try:
            last = self._store.get(table)
        except:
            last = []

        # data.index = data.index.tz_localize(tz).tz_convert('UTC')

        if len(last) > 0:
            last = last.append(data)
            last = last[~last.index.duplicated(keep='first')]
            last.sort_index(inplace=True)
            # TODO: guardar un màxim de mostres
        else:
            last = data

        self._store.append(table, last, format='t', append=False, data_columns=True)

    def remove_item(self, table):
        self._store.remove(table)

    def exist_grup(self, grup):
        """
        Retorna true si existeix el grup o false si no existeix.
        grup -- el nom del grup en string
        """
        # To do -  Comprovar si hi ha caracters estranys als strings [/...]
        return grup in [key for key in self._store.keys()]

    def close(self):
        """destructor de la classe"""
        print('iniciant el destructor')
        self._store.close()
