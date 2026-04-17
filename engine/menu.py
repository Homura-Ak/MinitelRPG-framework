# -*- coding: utf-8 -*-
"""
engine/menu.py
==============
Moteur de menus interactifs pour le Minitel.

Ce module expose :
  Menu       : menu classique (choix numérotés / lettres, rendu plein écran)
  Choice     : un choix de menu avec condition, sons et action
  StateEvent : événement déclenché au changement d'état (son + message)
  MenuExit   : exception pour quitter proprement un menu

Personnalisation du Menu
-------------------------
Toutes les options d'affichage, de timing et de navigation sont configurables
à l'instanciation. Les valeurs par défaut fonctionnent pour un Minitel 80×24.

Voir la docstring de Menu pour la liste complète des paramètres.
"""

import time
from typing import TYPE_CHECKING, Callable, Any

from .audio    import play_once, LoopPlayer
from .terminal import MinitelTerminal, COLS, LINES

if TYPE_CHECKING:
    from .state import SessionState


# ---------------------------------------------------------------------------
# Exception de sortie de menu
# ---------------------------------------------------------------------------

class MenuExit(Exception):
    """
    Levée pour quitter proprement la boucle d'un menu.
    Le menu parent reprend la main.

    Usage dans un CallbackAction :
        raise MenuExit()
        # ou via le trick lambda :
        CallbackAction(lambda t, s: (_ for _ in ()).throw(MenuExit()))
    """
    pass


# ---------------------------------------------------------------------------
# Choice : un choix de menu
# ---------------------------------------------------------------------------

class Choice:
    """
    Un choix dans un Menu.

    Paramètres
    ----------
    key       : touche à presser pour activer ce choix (ex: "1", "A", "Q")
                Insensible à la casse. La touche est stockée en majuscule.
    label     : texte affiché dans le menu à côté de la touche
    action    : objet avec méthode .run(term, state) — ou callable(term, state)
    condition : callable(state) -> bool
                Si None : choix toujours visible.
                Si False : le choix est masqué (et donc inactif).
    sounds    : dict de sons déclenchés lors de la sélection.
                Clé supportée : "select" → son joué quand ce choix est activé.
                Ex: sounds={"select": Sound("beep.wav", volume=0.5)}

    Exemple
    -------
        Choice(
            "5", "PROTOCOLE D'URGENCE",
            action    = urgence_action,
            condition = lambda state: state.get("contamination", False),
            sounds    = {"select": "sounds/alarm.wav"},
        )
    """

    def __init__(
        self,
        key:       str,
        label:     str,
        action,
        condition: Callable = None,
        sounds:    dict     = None,
    ):
        self.key       = key.upper()
        self.label     = label
        self.action    = action
        self.condition = condition
        self.sounds    = sounds or {}

    def is_visible(self, state: "SessionState") -> bool:
        """Retourne True si le choix doit être affiché (condition satisfaite ou None)."""
        if self.condition is None:
            return True
        try:
            return bool(self.condition(state))
        except Exception:
            return False

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """
        Exécute l'action associée au choix.
        Joue le son "select" avant si configuré.
        """
        play_once(self.sounds.get("select"))
        if callable(self.action) and not hasattr(self.action, "run"):
            self.action(term, state)
        else:
            self.action.run(term, state)


# ---------------------------------------------------------------------------
# StateEvent : événement sur changement d'état
# ---------------------------------------------------------------------------

class StateEvent:
    """
    Déclenché automatiquement quand une clé d'état prend une valeur donnée.

    Paramètres
    ----------
    key          : clé de l'état surveillée (ex: "contamination")
    value        : valeur déclenchante (ex: True). Si None : tout changement déclenche.
    sound        : son joué quand l'événement se déclenche (str ou Sound)
    message      : texte d'alerte court affiché sur la ligne LINES-1
    message_file : fichier texte affiché en plein écran (prioritaire sur message)
    callback     : fonction(term, state) appelée en supplément

    Exemple
    -------
        menu.on_state(
            "contamination",
            value        = True,
            sound        = Sound("alarm.wav", volume=0.8),
            message_file = "assets/contamination_alert.txt",
        )
        menu.on_state(
            "contamination",
            value   = False,
            sound   = "beep.wav",
            message = "Contamination neutralisee.",
        )
    """

    def __init__(
        self,
        key:          str,
        value:        Any      = None,
        sound                = None,
        message:      str      = None,
        message_file: str      = None,
        callback:     Callable = None,
    ):
        self.key          = key
        self.value        = value
        self.sound        = sound
        self.message      = message
        self.message_file = message_file
        self.callback     = callback

    def matches(self, new_value: Any) -> bool:
        """Retourne True si la nouvelle valeur correspond à la condition."""
        return self.value is None or new_value == self.value

    def fire(self, term: MinitelTerminal, state: "SessionState", new_value: Any):
        """Déclenche l'événement : son, message, callback."""
        if not self.matches(new_value):
            return
        if self.sound:
            play_once(self.sound)
        if self.message_file and term:
            self._show_file(term, self.message_file)
        elif self.message and term:
            term.send(term.seq_cup(LINES - 1, 1))
            term.send(term.seq_el())
            term.send(f"[!] {self.message}"[: COLS])
        if self.callback:
            try:
                self.callback(term, state)
            except Exception as e:
                print(f"[event] callback error: {e}")

    def _show_file(self, term: MinitelTerminal, path: str):
        """Affiche un fichier texte en plein écran (pour les alertes importantes)."""
        import os
        term.clear()
        if not os.path.isfile(path):
            term.at(LINES // 2, 2, f"[Fichier introuvable : {path}]")
            term.wait_enter()
            return
        with open(path, "r", encoding="latin-1", errors="ignore") as f:
            lines = f.read().splitlines()
        top    = 1
        bottom = LINES - 1
        window = bottom - top + 1
        term.send(term.seq_cup(top, 1))
        for ln in lines[: window]:
            ln = MinitelTerminal.safe_line(ln)
            term.send(ln[: COLS])
            term.send(term.seq_nel())
            time.sleep(0.03)
        term.at(LINES, 1, "[Appuyez ENTREE pour continuer]")
        term.wait_enter()


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------

class Menu:
    """
    Menu interactif affiché sur le Minitel.

    L'utilisateur tape une touche (ou plusieurs + Entrée) pour sélectionner
    un choix. Les choix conditionnels apparaissent ou disparaissent selon
    l'état de session.

    Paramètres de personnalisation
    --------------------------------
    header          : texte de la ligne 1 (titre principal, vidéo inverse)
    subheader       : texte de la ligne 2 (sous-titre, vidéo inverse)
                      Si vide, affiche une ligne de "=" par défaut.
    footer          : texte de la dernière ligne (invite de saisie)
                      Ex: "[ENTRER COMMANDE]", "CHOIX > "
    header_prefix   : préfixe du header (défaut "# - ")
                      Mettre "" pour un header sans préfixe.
    typing_sound    : son joué en boucle pendant l'affichage des choix
                      (str ou Sound avec volume)
    menu_row_start  : ligne de début des choix (défaut 7)
                      Augmenter si le header occupe plus de place.
    choice_indent   : colonne de début des choix (défaut 4)
    choice_format   : format d'une ligne de choix (défaut "{key} - {label}")
                      Peut être surchargé : "{key}) {label}", "  [{key}] {label}", etc.
    unknown_msg     : message affiché si la touche ne correspond à aucun choix
                      (défaut "[?] Commande inconnue : {key}")

    Méthodes de configuration
    --------------------------
    add_choice(key, label, action, condition, sounds)
        Ajoute un choix au menu. Retourne self pour le chaînage fluent.

    on_state(key, value, sound, message, message_file, callback)
        Enregistre un événement déclenché quand state[key] == value.

    Exemple
    -------
        menu = Menu(
            header        = "SEEGSON BIOS 5.3.09.63",
            subheader     = "APOLLO STATION — HADLEY'S HOPE",
            footer        = "[ENTRER COMMANDE] > ",
            typing_sound  = Sound("assets/sounds/typing.wav", volume=0.3),
            menu_row_start = 8,
            choice_indent  = 6,
            choice_format  = "{key}) {label}",
            unknown_msg    = "[ERREUR] Commande inconnue : {key}",
        )
        menu.add_choice("1", "A.P.O.L.L.O",    action=apollo)
        menu.add_choice("2", "POWER STATUS",    action=TextPage("power.txt"))
        menu.add_choice(
            "5", "CONFINEMENT",
            action    = containment_menu,
            condition = lambda state: state.get("contamination", False),
            sounds    = {"select": "sounds/alarm.wav"},
        )
        menu.on_state("contamination", value=True,
                      sound="sounds/horn.wav", message="!!! CONTAMINATION !!!")
    """

    def __init__(
        self,
        header:          str   = "",
        subheader:       str   = "",
        footer:          str   = "[ENTER QUERY]",
        header_prefix:   str   = "# - ",
        typing_sound           = None,
        menu_row_start:  int   = 7,
        choice_indent:   int   = 4,
        choice_format:   str   = "{key} - {label}",
        unknown_msg:     str   = "[?] Commande inconnue : {key}",
    ):
        self.header          = header
        self.subheader       = subheader
        self.footer          = footer
        self.header_prefix   = header_prefix
        self.typing_sound    = typing_sound
        self.menu_row_start  = menu_row_start
        self.choice_indent   = choice_indent
        self.choice_format   = choice_format
        self.unknown_msg     = unknown_msg
        self._choices: list[Choice]     = []
        self._events:  list[StateEvent] = []

    # ------------------------------------------------------------------
    # API de configuration (fluent)
    # ------------------------------------------------------------------

    def add_choice(
        self,
        key:       str,
        label:     str,
        action,
        condition: Callable = None,
        sounds:    dict     = None,
    ) -> "Menu":
        """
        Ajoute un choix au menu.

        Paramètres
        ----------
        key       : touche à presser (ex: "1", "A", "Q")
        label     : texte affiché
        action    : objet .run(term, state) ou callable(term, state)
        condition : callable(state) -> bool — masque le choix si False
        sounds    : {"select": son_ou_Sound} — son joué à la sélection

        Retourne self pour le chaînage fluent.
        """
        self._choices.append(Choice(key, label, action, condition, sounds))
        return self

    def on_state(
        self,
        key:          str,
        value:        Any      = None,
        sound                = None,
        message:      str      = None,
        message_file: str      = None,
        callback:     Callable = None,
    ) -> "Menu":
        """
        Enregistre un événement déclenché quand state[key] == value.

        Paramètres
        ----------
        key          : clé de l'état à surveiller
        value        : valeur déclenchante (None = tout changement)
        sound        : son joué lors du déclenchement (str ou Sound)
        message      : texte court affiché sur la ligne LINES-1
        message_file : fichier texte affiché en plein écran (prioritaire)
        callback     : fonction(term, state) appelée en plus

        Retourne self pour le chaînage fluent.
        """
        self._events.append(StateEvent(key, value, sound, message, message_file, callback))
        return self

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """
        Lance la boucle interactive du menu.

        Retourne quand l'utilisateur active un choix qui lève MenuExit,
        ou quand le code de campagne fait remonter une exception.
        """
        # Enregistre les watchers d'état → événements automatiques
        self._register_watchers(term, state)

        self._render(term, state)

        max_input = COLS - len(self.footer) - 2
        buf: list[str] = []
        input_col = len(self.footer) + 2

        term.send(term.seq_cup(LINES, input_col))

        while True:
            b = term.read(1)
            if not b:
                continue
            ch = b.decode("latin-1", errors="ignore")

            if ch in ("\r", "\n"):
                # Touche Entrée : traite la saisie
                query = "".join(buf).strip().upper()
                buf   = []
                # Efface la saisie
                term.send(term.seq_cup(LINES, input_col))
                term.send(" " * max_input)
                term.send(term.seq_cup(LINES, input_col))

                if query:
                    try:
                        self._handle(query, term, state)
                    except MenuExit:
                        return
                    # Re-render après retour d'une action
                    self._render(term, state)
                    term.send(term.seq_cup(LINES, input_col))
                continue

            if ord(ch) in (8, 127):
                # Backspace
                if buf:
                    buf.pop()
                    col = input_col + len(buf)
                    term.send(term.seq_cup(LINES, col))
                    term.send(" ")
                    term.send(term.seq_cup(LINES, col))
                continue

            if 32 <= ord(ch) <= 126 and len(buf) < max_input:
                buf.append(ch)
                term.send(ch)

    # ------------------------------------------------------------------
    # Gestion des choix
    # ------------------------------------------------------------------

    def _handle(self, key: str, term: MinitelTerminal, state: "SessionState"):
        """
        Recherche le choix correspondant à key et l'exécute.
        Affiche unknown_msg si aucun choix ne correspond.
        """
        for choice in self._choices:
            if choice.key == key and choice.is_visible(state):
                choice.run(term, state)
                return
        # Commande inconnue
        msg = self.unknown_msg.format(key=key)
        term.send(term.seq_cup(LINES - 1, 1))
        term.send(term.seq_el())
        term.send(msg[: COLS])

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _render(self, term: MinitelTerminal, state: "SessionState"):
        """Redessine le menu complet : header, séparateur, choix visibles, footer."""
        init = term.seq_is2()
        if init:
            term.send(init)
        term.clear()

        self._draw_header(term)

        # Séparateur ligne 3
        term.at(3, 2, "_" * (COLS - 2))

        # Affichage des choix visibles
        visible = [c for c in self._choices if c.is_visible(state)]
        row     = self.menu_row_start
        for choice in visible:
            line = self.choice_format.format(key=choice.key, label=choice.label)
            with LoopPlayer(self.typing_sound) if self.typing_sound else _NullCtx():
                term.at(row, self.choice_indent, line[: COLS - self.choice_indent - 2])
            row += 1
            if row > LINES - 3:
                break  # plus assez de place, on arrête

        # Footer
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(self.footer[: COLS - 2])

    def _draw_header(self, term: MinitelTerminal):
        """
        Dessine les 2 lignes de header en vidéo inverse.

        Ligne 1 : "{header_prefix}{header}" centré
        Ligne 2 : subheader (ou "===...===" si vide)
        """
        # Ligne 1
        title = f"{self.header_prefix}{self.header} "
        col   = max(2, (COLS - len(title)) // 2 + 1)
        term.send(term.seq_cup(1, 1))
        term.send(term.seq_smso())
        term.send(" " * COLS)
        term.send(term.seq_rmso())
        term.send(term.seq_cup(1, col))
        term.send(term.seq_smso())
        term.send(title[: COLS - 2])
        term.send(term.seq_rmso())

        # Ligne 2
        sub = self.subheader or ("=" * (COLS - 8))
        term.send(term.seq_cup(2, 1))
        term.send(term.seq_smso())
        term.send(" " * COLS)
        term.send(term.seq_rmso())
        term.send(term.seq_cup(2, 4))
        term.send(term.seq_smso())
        term.send(sub[: COLS - 8])
        term.send(term.seq_rmso())

    # ------------------------------------------------------------------
    # Watchers d'état
    # ------------------------------------------------------------------

    def _register_watchers(self, term: MinitelTerminal, state: "SessionState"):
        """Branche chaque StateEvent sur le système de watchers de SessionState."""
        for event in self._events:
            def make_handler(ev: StateEvent):
                def handler(new_value):
                    ev.fire(term, state, new_value)
                return handler
            state.watch(event.key, make_handler(event))


# ---------------------------------------------------------------------------
# Null context manager
# ---------------------------------------------------------------------------

class _NullCtx:
    """Context manager no-op pour les sons optionnels."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
