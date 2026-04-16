# -*- coding: utf-8 -*-
"""
engine/menu.py
Moteur de menus :
  - Choix conditionnels (visibles/actifs selon l'état de session)
  - Actions : TextPage, LLMTerminal, sous-Menu, CallbackAction
  - Événements déclenchés au changement d'état (son, texte d'alerte)
  - Rendu Minitel avec header/footer personnalisables
"""

import time
from typing import TYPE_CHECKING, Callable, Any

from .audio    import play_once, LoopPlayer
from .terminal import MinitelTerminal, COLS, LINES


# ---------------------------------------------------------------------------
# Exception pour quitter un menu
# ---------------------------------------------------------------------------

class MenuExit(Exception):
    """Levée pour quitter proprement la boucle d'un menu (retour au parent)."""
    pass

if TYPE_CHECKING:
    from .state   import SessionState


# ---------------------------------------------------------------------------
# Choix de menu
# ---------------------------------------------------------------------------

class Choice:
    """
    Un choix dans un menu.

    key       : touche à presser (ex: "1", "A")
    label     : texte affiché
    action    : objet avec méthode .run(term, state)
                ou callable (term, state) -> None
    condition : callable(state) -> bool  (None = toujours visible)
    sounds    : {"select": "beep.wav"}
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
        if self.condition is None:
            return True
        try:
            return bool(self.condition(state))
        except Exception:
            return False

    def run(self, term: MinitelTerminal, state: "SessionState"):
        play_once(self.sounds.get("select"))
        if callable(self.action) and not hasattr(self.action, "run"):
            self.action(term, state)
        else:
            self.action.run(term, state)


# ---------------------------------------------------------------------------
# Événement d'état
# ---------------------------------------------------------------------------

class StateEvent:
    """
    Déclenché quand une clé d'état prend une valeur donnée.

    key       : clé surveillée
    value     : valeur déclenchante (None = tout changement)
    sound     : fichier WAV à jouer
    message   : texte d'alerte affiché sur le Minitel (ligne LINES-1)
    callback  : fonction(term, state) appelée en plus
    """

    def __init__(
        self,
        key:          str,
        value:        Any      = None,
        sound:        str      = None,
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
        return self.value is None or new_value == self.value

    def fire(self, term: MinitelTerminal, state: "SessionState", new_value: Any):
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
        import os, time
        term.clear()
        if not os.path.isfile(path):
            term.at(LINES // 2, 2, f"[Fichier introuvable : {path}]")
            term.wait_enter()
            return
        with open(path, 'r', encoding='latin-1', errors='ignore') as f:
            lines = f.read().splitlines()
        top, bottom = 1, LINES - 1
        window = bottom - top + 1
        term.send(term.seq_cup(top, 1))
        for ln in lines[:window]:
            ln = MinitelTerminal.safe_line(ln)
            term.send(ln[:COLS])
            term.send(term.seq_nel())
            time.sleep(0.03)
        term.at(LINES, 1, "[Appuyez ENTREE pour continuer]")
        term.wait_enter()


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

class Menu:
    """
    Menu interactif affiché sur le Minitel.

    Usage :
        m = Menu(header="SEEGSON BIOS 5.3.09.63")
        m.add_choice("1", "A.P.O.L.L.O", action=apollo_terminal)
        m.add_choice("2", "POWER STATUS", action=TextPage("power.txt"),
                     condition=lambda s: s.get("power_on", True))
        m.on_state("contamination", value=True,
                   sound="alert.wav", message="CONTAMINATION DETECTED")
    """

    def __init__(
        self,
        header:       str  = "",
        subheader:    str  = "",
        footer:       str  = "[ENTER QUERY]",
        typing_sound: str  = None,
        menu_row_start: int = 7,
    ):
        self.header         = header
        self.subheader      = subheader
        self.footer         = footer
        self.typing_sound   = typing_sound
        self.menu_row_start = menu_row_start
        self._choices: list[Choice]     = []
        self._events:  list[StateEvent] = []

    # ------------------------------------------------------------------
    # API fluent
    # ------------------------------------------------------------------

    def add_choice(
        self,
        key:       str,
        label:     str,
        action,
        condition: Callable = None,
        sounds:    dict     = None,
    ) -> "Menu":
        self._choices.append(Choice(key, label, action, condition, sounds))
        return self

    def on_state(
        self,
        key:          str,
        value:        Any      = None,
        sound:        str      = None,
        message:      str      = None,
        message_file: str      = None,
        callback:     Callable = None,
    ) -> "Menu":
        """
        Enregistre un événement déclenché quand state[key] == value.
        """
        self._events.append(StateEvent(key, value, sound, message, message_file, callback))
        return self

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """Lance la boucle de menu. Retourne quand l'utilisateur quitte."""

        # Brancher les watchers d'état → événements immédiats
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
                query = "".join(buf).strip().upper()
                buf   = []
                # Effacer la saisie
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
        for choice in self._choices:
            if choice.key == key and choice.is_visible(state):
                choice.run(term, state)
                return
        # Commande inconnue
        term.send(term.seq_cup(LINES - 1, 1))
        term.send(term.seq_el())
        term.send(f"[?] Commande inconnue : {key}"[: COLS])

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def _render(self, term: MinitelTerminal, state: "SessionState"):
        """Redessine le menu complet (header + choix visibles + footer)."""
        init = term.seq_is2()
        if init:
            term.send(init)
        term.clear()

        # Header (lignes 1-2 en vidéo inverse)
        self._draw_header(term)

        # Séparateur ligne 3
        term.at(3, 2, "_" * (COLS - 2))

        # Choix visibles
        visible = [c for c in self._choices if c.is_visible(state)]
        row = self.menu_row_start
        for choice in visible:
            line = f"{choice.key} - {choice.label}"
            with LoopPlayer(self.typing_sound) if self.typing_sound else _NullCtx():
                term.at(row, 4, line[: COLS - 8])
            row += 1
            if row > LINES - 3:
                break  # pas assez de place

        # Footer (dernière ligne)
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(self.footer[: COLS - 2])

    def _draw_header(self, term: MinitelTerminal):
        """Dessine les 2 lignes de header en vidéo inverse."""
        # Ligne 1
        title = f"# - {self.header} "
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
        for event in self._events:
            # Closure pour capturer event
            def make_handler(ev: StateEvent):
                def handler(new_value):
                    ev.fire(term, state, new_value)
                return handler
            state.watch(event.key, make_handler(event))


# ---------------------------------------------------------------------------
# Null context manager
# ---------------------------------------------------------------------------

class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *_): pass
