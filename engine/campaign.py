# -*- coding: utf-8 -*-
"""
engine/campaign.py
Classe Campaign : point d'entrée du framework.
Orchestre Boot → Menu principal → boucle de session.
"""

import os
import sys
from typing import TYPE_CHECKING

from .terminal import MinitelTerminal
from .state    import SessionState

if TYPE_CHECKING:
    from .actions import Boot
    from .menu    import Menu


class Campaign:
    """
    Orchestre toute la session de jeu.

    Usage minimal :
        campaign = Campaign(device="/dev/ttyUSB0", baud=4800)
        campaign.boot = Boot(...)
        campaign.menu = Menu(...)
        campaign.run()

    Paramètres :
        device        : port série (ex: /dev/ttyUSB0)
        baud          : débit en bauds (4800 pour Minitel)
        termname      : type de terminal terminfo
        save_file     : chemin du fichier de sauvegarde d'état JSON
                        (None = pas de persistance entre sessions)
        loop_on_exit  : si True, relance le boot après /exit du LLM
    """

    def __init__(
        self,
        device:       str  = "/dev/ttyUSB0",
        baud:         int  = 4800,
        termname:     str  = None,
        save_file:    str  = None,
        loop_on_exit: bool = True,
    ):
        self.device       = device
        self.baud         = baud
        self.termname     = termname
        self.save_file    = save_file
        self.loop_on_exit = loop_on_exit

        self.boot: "Boot | None" = None
        self.menu: "Menu | None" = None

        self._term:  MinitelTerminal | None = None
        self._state: SessionState    | None = None

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------

    def run(self):
        """Lance la campagne. Bloquant jusqu'à KeyboardInterrupt."""
        self._term  = MinitelTerminal(self.device, self.baud, self.termname)
        self._state = SessionState(self.save_file)

        self._term.open()

        try:
            while True:
                # --- Séquence de boot ---
                if self.boot is not None:
                    confirmed = self.boot.run(self._term, self._state)
                    if not confirmed:
                        # L'utilisateur n'a pas confirmé → reboucle
                        continue

                # --- Menu principal ---
                if self.menu is not None:
                    self.menu.run(self._term, self._state)

                # --- Après le menu ---
                if not self.loop_on_exit:
                    break
                # Sinon, reboucle (revient au boot)

        except KeyboardInterrupt:
            pass
        finally:
            try:
                self._term.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Accès à l'état depuis la campagne (utile pour les callbacks)
    # ------------------------------------------------------------------

    @property
    def state(self) -> SessionState:
        if self._state is None:
            self._state = SessionState(self.save_file)
        return self._state
