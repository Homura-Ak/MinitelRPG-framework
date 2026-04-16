# -*- coding: utf-8 -*-
"""
engine/actions.py
Actions disponibles dans les menus :
  - Boot         : séquence de démarrage (art, logo, sons, barre de chargement)
  - TextPage     : affichage paginé d'un fichier texte
  - LLMTerminal  : interface de chat avec un LLM
  - SubMenu      : renvoi vers un autre Menu (défini dans menu.py)
  - CallbackAction : fonction Python arbitraire
"""

import os
import sys
import time
import subprocess
from typing import TYPE_CHECKING, Callable

from .audio    import LoopPlayer, play_once, play_async
from .terminal import MinitelTerminal, COLS, LINES

if TYPE_CHECKING:
    from .state import SessionState
    from .menu  import Menu


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _resolve(path: str) -> str:
    """Résout un chemin relatif par rapport au CWD."""
    return os.path.abspath(path)


def _read_lines(path: str) -> list[str]:
    with open(path, "r", encoding="latin-1", errors="ignore") as f:
        return f.read().splitlines()


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

class Boot:
    """
    Séquence de démarrage :
      1. Affiche l'art ASCII + son de boot
      2. Prompt BOOT ? (Y/N)
      3. Défilement du logo avec son de frappe
      4. Barre de chargement
      5. Son final → retour au moteur
    """

    def __init__(
        self,
        art:                   str   = None,
        scroll_text:           str   = None,   # texte qui défile après confirmation
        logo:                  str   = None,   # logo affiché quelques secondes après le défilement
        logo_display_duration: float = 3.0,    # durée d'affichage du logo en secondes
        boot_sound:            str   = None,
        beep_sound:            str   = None,
        typing_sound:          str   = None,
        loading_sound:         str   = None,
        final_sound:           str   = None,
        loading_duration:      int   = 10,
        scroll_delay:          float = 0.10,
        prompt:                str   = "BOOT ? (Y/N) : ",
    ):
        self.art                   = art
        self.scroll_text           = scroll_text
        self.logo                  = logo
        self.logo_display_duration = logo_display_duration
        self.boot_sound            = boot_sound
        self.beep_sound            = beep_sound
        self.typing_sound          = typing_sound
        self.loading_sound         = loading_sound
        self.final_sound           = final_sound
        self.loading_duration      = loading_duration
        self.scroll_delay          = scroll_delay
        self.prompt                = prompt

    def run(self, term: MinitelTerminal, state: "SessionState") -> bool:
        term.clear()
        self._show_art(term)
        play_async(self.boot_sound)

        # Prompt
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(self.prompt)
        ans = term.read_line(echo=True, maxlen=3).strip().upper()

        if ans != "Y":
            return False

        term.clear()
        play_once(self.beep_sound)

        # 1. Affichage du logo quelques secondes
        if self.logo:
            self._show_logo(term)

        # 2. Défilement du scroll_text
        if self.scroll_text:
            self._scroll_file(term, self.scroll_text)

        # 3. Barre de chargement
        self._loading_bar(term)
        play_once(self.final_sound)
        return True

    def _show_art(self, term: MinitelTerminal):
        if not self.art or not os.path.isfile(self.art):
            return
        with open(self.art, 'rb') as f:
            lines = f.read().split(b'\n')
        for r, ln in enumerate(lines[: LINES - 1], start=1):
            term.send(term.seq_cup(r, 1))
            term.send(term.seq_el())
            term.send(ln)  # envoie les bytes bruts incluant les séquences ESC

    def _scroll_file(self, term: MinitelTerminal, path: str):
        """Fait défiler un fichier texte ligne par ligne."""
        if not os.path.isfile(path):
            return
        lines  = _read_lines(path)
        top, bottom = 1, LINES - 1
        window = bottom - top + 1

        term.clear_window(top, bottom)
        term.civis()

        with LoopPlayer(self.typing_sound) if self.typing_sound else _NullCtx():
            filled = 0
            for raw in lines:
                ln = MinitelTerminal.safe_line(raw)[: COLS]
                if filled < window:
                    term.send(term.seq_cup(top + filled, 1))
                    term.send(term.seq_el())
                    term.send(ln)
                    filled += 1
                else:
                    term.send(term.seq_cup(top, 1))
                    term.send(term.seq_dl1())
                    term.send(term.seq_cup(bottom, 1))
                    term.send(term.seq_el())
                    term.send(ln)
                time.sleep(self.scroll_delay)

        term.cnorm()

    def _show_logo(self, term: MinitelTerminal):
        """Affiche le logo.txt tel quel pendant logo_display_duration secondes."""
        if not os.path.isfile(self.logo):
            return
        lines = _read_lines(self.logo)
        term.clear()
        term.civis()
        term.send(term.seq_cup(1, 1))
        for ln in lines[: LINES - 1]:
            term.send(MinitelTerminal.safe_line(ln)[: COLS])
            term.send(term.seq_nel())
        time.sleep(self.logo_display_duration)
        term.cnorm()

    def _loading_bar(self, term: MinitelTerminal):
        with LoopPlayer(self.loading_sound) if self.loading_sound else _NullCtx():
            start    = time.time()
            last_pct = -1
            while True:
                elapsed = time.time() - start
                if elapsed > self.loading_duration:
                    break
                pct = int((elapsed / self.loading_duration) * 100)
                if pct != last_pct:
                    filled = int((pct / 100.0) * COLS)
                    term.send(term.seq_cup(LINES, 1))
                    term.send(("#" * filled).ljust(COLS)[: COLS])
                    last_pct = pct
                time.sleep(0.05)
        term.send(term.seq_cup(LINES, 1))
        term.send("#" * COLS)


# ---------------------------------------------------------------------------
# TextPage
# ---------------------------------------------------------------------------

class TextPage:
    """
    Affiche un fichier texte de façon paginée (20 lignes par page).
    Avec son de frappe et retour au menu parent à la fin.
    """

    def __init__(self, path: str, typing_sound: str = None, scroll_delay: float = 0.02):
        self.path         = path
        self.typing_sound = typing_sound
        self.scroll_delay = scroll_delay

    def run(self, term: MinitelTerminal, state: "SessionState"):
        if not os.path.isfile(self.path):
            term.at(LINES, 1, f"[Fichier introuvable : {self.path}]")
            term.wait_enter()
            return

        lines  = [MinitelTerminal.safe_line(ln).expandtabs(8)
                  for ln in _read_lines(self.path)]
        top, bottom = 4, LINES - 1
        window = bottom - top + 1
        idx    = 0

        while True:
            term.clear_window(top, bottom)
            term.send(term.seq_cup(top, 1))

            with LoopPlayer(self.typing_sound) if self.typing_sound else _NullCtx():
                written = 0
                while idx < len(lines) and written < window:
                    ln = lines[idx][: COLS]
                    term.send(ln)
                    term.send(term.seq_nel())
                    time.sleep(self.scroll_delay)
                    idx     += 1
                    written += 1

            if idx >= len(lines):
                term.at(LINES, 1, "[FIN. Appuyez ENTREE pour revenir]")
                term.wait_enter()
                return
            else:
                term.at(LINES, 1, "[SUITE. Appuyez ENTREE pour continuer]")
                term.wait_enter()


# ---------------------------------------------------------------------------
# LLMTerminal
# ---------------------------------------------------------------------------

class LLMTerminal:
    """
    Interface de chat LLM affichée sur le Minitel.
    Personnalisable : nom, header, prompt système, provider, sons.
    """

    def __init__(
        self,
        name:             str,
        header:           str         = None,
        prompt:           str         = None,
        prompt_file:      str         = None,
        provider:         str         = "openai",
        model:            str         = "gpt-4o-mini",
        api_key:          str         = None,
        base_url:         str         = None,
        sounds:           dict        = None,
        exit_command:     str         = "/exit",
        boot_prompt:      str         = None,
        boot_logo:        str         = None,
        boot_sound:       str         = None,
        boot_confirm:     str         = "Y",
        input_prompt:     str         = None,
    ):
        self.name         = name
        self.header       = header or name
        self.exit_command = exit_command
        self.sounds       = sounds or {}
        self.boot_prompt  = boot_prompt
        self.boot_logo    = boot_logo
        self.boot_sound   = boot_sound
        self.boot_confirm = boot_confirm.upper()
        self.input_prompt = input_prompt or f"[{self.name}]> "

        if prompt_file and os.path.isfile(prompt_file):
            with open(prompt_file, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        elif prompt:
            system_prompt = prompt
        else:
            system_prompt = f"You are {name}, an onboard computer AI."

        from .llm import make_provider
        self._provider_cfg = dict(
            provider      = provider,
            model         = model,
            system_prompt = system_prompt,
            api_key       = api_key,
            base_url      = base_url,
        )
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from .llm import make_provider
            self._llm = make_provider(**self._provider_cfg)
        return self._llm

    def run(self, term: MinitelTerminal, state: "SessionState"):
        # --- Séquence de boot optionnelle ---
        if self.boot_prompt:
            term.clear()
            term.send(term.seq_cup(LINES, 1))
            term.send(self.boot_prompt)
            ans = term.read_line(echo=True, maxlen=3).strip().upper()
            if ans != self.boot_confirm:
                return

        if self.boot_logo and os.path.isfile(self.boot_logo):
            self._scroll_boot_logo(term)

        llm = self._get_llm()
        llm.reset_history()

        self._render_header(term)
        self._render_input_prompt(term, "")

        while True:
            user_input = self._read_input(term)
            if user_input.strip().lower() == self.exit_command.lower():
                break

            # Afficher [YOU] et [NOM] avant la réponse
            start_row = self._display_exchange(term, user_input)

            # Afficher "..." et jouer le son en boucle pendant l'attente
            #term.at(LINES - 1, 1, ". . .")
            term.at(start_row, 1, "THINKING")
            with LoopPlayer(self.sounds.get("thinking")) if self.sounds.get("thinking") else _NullCtx():
                try:
                    response = self._get_llm().ask(user_input, state)
                except Exception as e:
                    response = f"[SYSTEM ERROR: {e}]"

            self._display_response(term, response, start_row)
            self._render_input_prompt(term, "")

    def _scroll_boot_logo(self, term: MinitelTerminal):
        lines  = _read_lines(self.boot_logo)
        top, bottom = 1, LINES - 1
        window = bottom - top + 1

        term.clear_window(top, bottom)
        term.civis()

        with LoopPlayer(self.boot_sound) if self.boot_sound else _NullCtx():
            filled = 0
            for raw in lines:
                ln = MinitelTerminal.safe_line(raw)[: COLS]
                if filled < window:
                    term.send(term.seq_cup(top + filled, 1))
                    term.send(term.seq_el())
                    term.send(ln)
                    filled += 1
                else:
                    term.send(term.seq_cup(top, 1))
                    term.send(term.seq_dl1())
                    term.send(term.seq_cup(bottom, 1))
                    term.send(term.seq_el())
                    term.send(ln)
                time.sleep(0.10)

        term.cnorm()

    def _render_header(self, term: MinitelTerminal):
        init = term.seq_is2()
        if init:
            term.send(init)
        term.clear()

        title = f"# - {self.header} "
        col   = max(2, (COLS - len(title)) // 2 + 1)
        with LoopPlayer(self.sounds.get("typing")) if self.sounds.get("typing") else _NullCtx():
            term.at(1, col, title, reverse=True)

        term.at(2, 2, ("=" * 24).ljust(COLS - 1), reverse=True)
        term.send(term.seq_rmso())
        term.send(" ")
        term.at(3, 2, "_" * (COLS - 2))
        term.at(LINES, 1, f"[{self.input_prompt}]> ")

    def _render_input_prompt(self, term: MinitelTerminal, value: str):
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(f"[{self.input_prompt}]> {value}")

    def _read_input(self, term: MinitelTerminal) -> str:
        prompt_len = len(f"[{self.input_prompt}]> ")
        return term.read_line(echo=True, maxlen=COLS - prompt_len)

    def _display_exchange(self, term: MinitelTerminal, user_input: str) -> int:
        # Affiche [YOU] + question + [NOM], retourne la ligne courante apres
        top = 4
        term.clear_window(top, LINES - 2)
        term.send(term.seq_cup(top, 1))
        term.send(term.seq_nel())
        #term.send(term.seq_smso()) #Début du fond blanc
        term.send("[YOU] "[:COLS])
        #term.send(term.seq_rmso()) #Fin du fond blanc
        #term.send(term.seq_nel())
        you_line = MinitelTerminal.safe_line(user_input)[:COLS]
        term.send(you_line)
        #term.send(term.seq_nel())
        #term.send(term.seq_nel())
        #term.send(term.seq_smso())
        #term.send(f"[{self.name}]"[:COLS])
        #term.send(term.seq_rmso())
        #term.send(term.seq_nel())
        return top + 3  # [YOU] + question + vide + [NOM]

    def _display_response(self, term: MinitelTerminal, text: str, start_row: int = 4):
        # Affiche la réponse a partir de start_row jusqu'a LINES-2
        bottom = LINES - 2
        window = bottom - start_row + 1

        lines = []
        for raw in text.splitlines():
            raw = MinitelTerminal.safe_line(raw)
            while len(raw) > COLS:
                lines.append(raw[:COLS])
                raw = raw[COLS:]
            lines.append(raw)

        term.send(term.seq_cup(start_row, 1))  # repositionner le curseur
        with LoopPlayer(self.sounds.get("typing")) if self.sounds.get("typing") else _NullCtx():
            for ln in lines[:window]:
                term.send(ln)
                term.send(term.seq_nel())
                time.sleep(0.02)

        if len(lines) > window:
            term.at(LINES - 1, 1, "[SUITE. ENTREE pour continuer]")
            term.wait_enter()
            rest = lines[window:]
            term.clear_window(4, bottom)
            term.send(term.seq_cup(4, 1))
            for ln in rest[:bottom - 4 + 1]:
                term.send(ln)
                term.send(term.seq_nel())


# ---------------------------------------------------------------------------
# CallbackAction
# ---------------------------------------------------------------------------

class CallbackAction:
    """
    Action arbitraire définie par une fonction Python.
    La fonction reçoit (term, state) et peut faire n'importe quoi.
    """

    def __init__(self, fn: Callable):
        self.fn = fn

    def run(self, term: MinitelTerminal, state: "SessionState"):
        self.fn(term, state)


# ---------------------------------------------------------------------------
# Null context manager (pour les sons optionnels)
# ---------------------------------------------------------------------------

class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *_): pass
