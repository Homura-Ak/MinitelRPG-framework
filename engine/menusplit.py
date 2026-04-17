# -*- coding: utf-8 -*-
"""
engine/menusplit.py
Menu deux colonnes style Alien Isolation / SEVASTOLINK.
"""

import os
import time
import threading
import subprocess
from typing import TYPE_CHECKING, Callable

from .audio    import LoopPlayer, play_once
from .terminal import MinitelTerminal, COLS, LINES

if TYPE_CHECKING:
    from .state import SessionState


LEFT_W     = 20
SEP_COL    = LEFT_W + 1
RIGHT_COL  = LEFT_W + 2
RIGHT_W    = COLS - RIGHT_COL + 1

CONTENT_TOP    = 5
CONTENT_BOTTOM = LINES - 2
CONTENT_H      = CONTENT_BOTTOM - CONTENT_TOP + 1

SEQ_UP    = b'\x1b[A'
SEQ_DOWN  = b'\x1b[B'
SEQ_RIGHT = b'\x1b[C'
SEQ_LEFT  = b'\x1b[D'


class AudioItem:
    def __init__(self, path: str, description: str = None, volume: float = 1.0):
        self.path        = path
        self.description = description or os.path.basename(path)
        self.volume      = volume


class SplitItem:
    def __init__(self, label: str, action, condition: Callable = None):
        self.label     = label
        self.action    = action
        self.condition = condition

    def is_visible(self, state: "SessionState") -> bool:
        if self.condition is None:
            return True
        try:
            return bool(self.condition(state))
        except Exception:
            return False


class SplitMenu:
    def __init__(
        self,
        header:        str  = "TERMINAL",
        folder_label:  str  = "FOLDERS",
        exit_key:      str  = "Q",
        footer:        str  = None,
        typing_sound:  str  = None,
    ):
        self.header       = header
        self.folder_label = folder_label
        self.exit_key     = exit_key.upper()
        self.footer       = footer or f"[HAUT/BAS] NAVIGUER  [DROITE] OUVRIR  [{exit_key}] QUITTER"
        self.typing_sound = typing_sound
        self._items: list[SplitItem] = []

    def add_item(self, label: str, action, condition: Callable = None) -> "SplitMenu":
        self._items.append(SplitItem(label, action, condition))
        return self

    def run(self, term: MinitelTerminal, state: "SessionState"):
        cursor = 0
        self._render_frame(term)
        visible = self._visible(state)
        if not visible:
            return
        self._render_list(term, visible, cursor)
        self._preview(term, state, visible, cursor)

        while True:
            seq = self._read_key(term)

            if seq in (self.exit_key.encode(), b'q', b'Q'):
                return

            elif seq == SEQ_UP:
                if cursor > 0:
                    cursor -= 1
                    self._render_list(term, visible, cursor)
                    self._preview(term, state, visible, cursor)

            elif seq == SEQ_DOWN:
                if cursor < len(visible) - 1:
                    cursor += 1
                    self._render_list(term, visible, cursor)
                    self._preview(term, state, visible, cursor)

            elif seq == SEQ_RIGHT:
                item = visible[cursor]
                from .actions import TextPage, LLMTerminal
                if isinstance(item.action, SplitMenu):
                    self._run_subfolder(term, state, item)
                elif isinstance(item.action, TextPage):
                    self._run_text_right(term, state, item)
                elif isinstance(item.action, LLMTerminal):
                    self._run_llm_right(term, state, item)
                elif isinstance(item.action, AudioItem):
                    self._run_audio_right(term, state, item)
                # Restaurer le footer principal au retour
                term.send(term.seq_cup(LINES, 1))
                term.send(term.seq_el())
                term.send(self.footer[:COLS])

            elif seq in (b'\r', b'\n'):
                item = visible[cursor]
                from .actions import TextPage, LLMTerminal
                if isinstance(item.action, TextPage):
                    self._run_text_right(term, state, item)
                elif isinstance(item.action, LLMTerminal):
                    self._run_llm_right(term, state, item)
                elif isinstance(item.action, AudioItem):
                    self._run_audio_right(term, state, item)
                else:
                    if callable(item.action) and not hasattr(item.action, 'run'):
                        item.action(term, state)
                    else:
                        item.action.run(term, state)
                    self._render_frame(term)
                    visible = self._visible(state)
                    if cursor >= len(visible):
                        cursor = max(0, len(visible) - 1)
                    self._render_list(term, visible, cursor)
                    self._preview(term, state, visible, cursor)

    def _run_text_right(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        from .actions import TextPage
        action: TextPage = item.action

        if not os.path.isfile(action.path):
            self._clear_right(term)
            term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
            term.send("[Fichier introuvable]")
            self._footer_right(term, "[GAUCHE] RETOUR")
            self._wait_left(term)
            return

        with open(action.path, 'r', encoding='latin-1', errors='ignore') as f:
            raw_lines = f.read().splitlines()

        lines = [MinitelTerminal.safe_line(ln).expandtabs(8) for ln in raw_lines]
        idx = 0
        window = CONTENT_H - 1

        while True:
            self._clear_right(term)
            term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
            term.send(term.seq_smso())
            term.send(f" {item.label} ".ljust(RIGHT_W))
            term.send(term.seq_rmso())

            with LoopPlayer(action.typing_sound) if action.typing_sound else _NullCtx():
                written = 0
                while idx < len(lines) and written < window:
                    row = CONTENT_TOP + 1 + written
                    ln  = lines[idx][:RIGHT_W]
                    term.send(term.seq_cup(row, RIGHT_COL))
                    term.send(ln)
                    time.sleep(action.scroll_delay)
                    idx     += 1
                    written += 1

            if idx >= len(lines):
                self._footer_right(term, "[GAUCHE] RETOUR")
                self._wait_left(term)
                return
            else:
                self._footer_right(term, "[ENTREE] SUITE  [GAUCHE] RETOUR")
                seq = self._read_key(term)
                if seq == SEQ_LEFT:
                    return

    def _run_llm_right(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        from .actions import LLMTerminal
        action: LLMTerminal = item.action

        llm = action._get_llm()
        llm.reset_history()

        self._clear_right(term)
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(term.seq_smso())
        term.send(f" {item.label} ".ljust(RIGHT_W))
        term.send(term.seq_rmso())

        resp_top    = CONTENT_TOP + 1
        resp_bottom = LINES - 2

        self._footer_right(term, f"[{action.input_prompt}]> ")

        while True:
            user_input = self._read_line_right(term, check_left=True)

            if user_input is None:
                return

            if not user_input.strip():
                self._footer_right(term, f"[{action.input_prompt}]> ")
                continue

            self._clear_right_content(term, resp_top, resp_bottom)
            term.send(term.seq_cup(resp_top, RIGHT_COL))
            term.send(term.seq_smso())
            term.send("[YOU] ")
            term.send(term.seq_rmso())
            you = MinitelTerminal.safe_line(user_input)[:RIGHT_W - 6]
            term.send(you)

            term.send(term.seq_cup(resp_top + 2, RIGHT_COL))
            term.send(term.seq_smso())
            term.send(f"[{action.name}]"[:RIGHT_W])
            term.send(term.seq_rmso())

            term.send(term.seq_cup(resp_top + 3, RIGHT_COL))
            term.send(". . . . . . . . . .")

            with LoopPlayer(action.sounds.get("thinking")) if action.sounds.get("thinking") else _NullCtx():
                try:
                    response = action._get_llm().ask(user_input, state)
                except Exception as e:
                    response = f"[SYSTEM ERROR: {e}]"

            self._clear_right_content(term, resp_top + 3, resp_bottom)
            lines = []
            for raw in response.splitlines():
                raw = MinitelTerminal.safe_line(raw)
                while len(raw) > RIGHT_W:
                    lines.append(raw[:RIGHT_W])
                    raw = raw[RIGHT_W:]
                lines.append(raw)

            window = resp_bottom - (resp_top + 3) + 1
            with LoopPlayer(action.sounds.get("typing")) if action.sounds.get("typing") else _NullCtx():
                for i, ln in enumerate(lines[:window]):
                    term.send(term.seq_cup(resp_top + 3 + i, RIGHT_COL))
                    term.send(ln)
                    time.sleep(0.02)

            self._footer_right(term, f"[{action.input_prompt}]> ")

    def _run_subfolder(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        subfolder: SplitMenu = item.action
        visible = [i for i in subfolder._items if i.is_visible(state)]
        if not visible:
            return

        cursor = 0
        self._footer_right(term, self._subfolder_footer(visible, cursor))
        # Surligner le premier item sans tout redessiner
        if visible:
            row = CONTENT_TOP + 1
            label = visible[0].label[:RIGHT_W - 3]
            term.send(term.seq_cup(row, RIGHT_COL))
            term.send(term.seq_smso())
            term.send(f" {label}".ljust(RIGHT_W))
            term.send(term.seq_rmso())

        while True:
            seq = self._read_key(term)

            if seq == SEQ_LEFT:
                return

            elif seq == SEQ_UP:
                if cursor > 0:
                    old = cursor
                    cursor -= 1
                    self._update_subfolder_cursor(term, visible, old, cursor)
                    self._footer_right(term, self._subfolder_footer(visible, cursor))

            elif seq == SEQ_DOWN:
                if cursor < len(visible) - 1:
                    old = cursor
                    cursor += 1
                    self._update_subfolder_cursor(term, visible, old, cursor)
                    self._footer_right(term, self._subfolder_footer(visible, cursor))

            elif seq in (b'\r', b'\n'):
                from .actions import TextPage, LLMTerminal
                sub_item = visible[cursor]
                if isinstance(sub_item.action, AudioItem):
                    self._run_audio_right(term, state, sub_item)
                elif isinstance(sub_item.action, TextPage):
                    self._run_text_right(term, state, sub_item)
                elif isinstance(sub_item.action, LLMTerminal):
                    self._run_llm_right(term, state, sub_item)
                else:
                    if callable(sub_item.action) and not hasattr(sub_item.action, 'run'):
                        sub_item.action(term, state)
                    else:
                        sub_item.action.run(term, state)
                    self._render_subfolder_right(term, item.label, visible, cursor)

    def _render_subfolder_right(self, term: MinitelTerminal, folder_label: str,
                                 visible: list, cursor: int):
        self._clear_right(term)
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(f" {folder_label} ".ljust(RIGHT_W))  # pas de vidéo inverse → non cliquable

        for i, sub_item in enumerate(visible[:CONTENT_H - 1]):
            row = CONTENT_TOP + 1 + i
            if row > CONTENT_BOTTOM:
                break
            label = sub_item.label[:RIGHT_W - 3]
            term.send(term.seq_cup(row, RIGHT_COL))
            if i == cursor:
                term.send(term.seq_smso())
                term.send(f" {label}".ljust(RIGHT_W))
                term.send(term.seq_rmso())
            else:
                term.send(f"  {label}".ljust(RIGHT_W))

        self._footer_right(term, "[HAUT/BAS] NAVIGUER  [DROITE] OUVRIR  [GAUCHE] RETOUR")

    def _subfolder_footer(self, visible: list, cursor: int) -> str:
        """Retourne le footer adapté au type de l'item courant."""
        from .actions import TextPage, LLMTerminal
        item = visible[cursor]
        if isinstance(item.action, AudioItem):
            return "[HAUT/BAS] NAVIGUER  [ENTREE] JOUER  [GAUCHE] RETOUR"
        return "[HAUT/BAS] NAVIGUER  [DROITE] OUVRIR  [GAUCHE] RETOUR"

    def _update_subfolder_cursor(self, term: MinitelTerminal, visible: list,
                                  old: int, new: int):
        """Redessine uniquement les deux lignes qui changent de curseur (ancienne et nouvelle)."""
        for i in (old, new):
            if i < 0 or i >= len(visible):
                continue
            row = CONTENT_TOP + 1 + i
            if row > CONTENT_BOTTOM:
                continue
            label = visible[i].label[:RIGHT_W - 3]
            term.send(term.seq_cup(row, RIGHT_COL))
            if i == new:
                term.send(term.seq_smso())
                term.send(f" {label}".ljust(RIGHT_W))
                term.send(term.seq_rmso())
            else:
                term.send(f"  {label}".ljust(RIGHT_W))

    def _run_audio_right(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        from .audio import _build_cmd
        action: AudioItem = item.action

        self._clear_right(term)

        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(term.seq_smso())
        term.send(f" {item.label} ".ljust(RIGHT_W))
        term.send(term.seq_rmso())

        term.send(term.seq_cup(CONTENT_TOP + 2, RIGHT_COL))
        term.send(action.description[:RIGHT_W])

        term.send(term.seq_cup(CONTENT_TOP + 4, RIGHT_COL))

        if not os.path.isfile(action.path):
            term.send("[ERREUR: fichier introuvable]")
            self._footer_right(term, "[GAUCHE] RETOUR")
            self._wait_left(term)
            return

        term.send("[ LECTURE EN COURS... ]")
        self._footer_right(term, "[GAUCHE] ARRETER")

        stop_event = threading.Event()

        def _play():
            cmd = _build_cmd(action.path, action.volume)
            try:
                p = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
                while p.poll() is None and not stop_event.is_set():
                    time.sleep(0.05)
                if p.poll() is None:
                    p.terminate()
            except FileNotFoundError:
                pass
            stop_event.set()

        t = threading.Thread(target=_play, daemon=True)
        t.start()

        while not stop_event.is_set():
            seq = self._read_key(term)
            if seq == SEQ_LEFT:
                stop_event.set()
                t.join(timeout=0.5)
                return

        t.join(timeout=0.5)
        term.send(term.seq_cup(CONTENT_TOP + 4, RIGHT_COL))
        term.send("[ LECTURE TERMINEE    ]")
        self._footer_right(term, "[GAUCHE] RETOUR")
        self._wait_left(term)

    def _clear_right(self, term: MinitelTerminal):
        for r in range(CONTENT_TOP, LINES - 1):
            term.send(term.seq_cup(r, RIGHT_COL))
            term.send(" " * RIGHT_W)

    def _clear_right_content(self, term: MinitelTerminal, top: int, bottom: int):
        for r in range(top, bottom + 1):
            term.send(term.seq_cup(r, RIGHT_COL))
            term.send(" " * RIGHT_W)

    def _footer_right(self, term: MinitelTerminal, text: str):
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(text[:COLS])

    def _wait_left(self, term: MinitelTerminal):
        while True:
            seq = self._read_key(term)
            if seq in (SEQ_LEFT, b'\r', b'\n', b'q', b'Q'):
                return

    def _read_line_right(self, term: MinitelTerminal, check_left: bool = False):
        buf = []
        max_len = RIGHT_W - 20
        while True:
            b = term.read(1)
            if not b:
                continue
            if b == b'\x1b':
                b2 = term.read(1)
                if b2 == b'[':
                    b3 = term.read(1)
                    if check_left and b3 == b'D':
                        return None
                continue
            ch = b.decode('latin-1', errors='ignore')
            if ch in ('\r', '\n'):
                return ''.join(buf)
            if ord(ch) in (8, 127):
                if buf:
                    buf.pop()
                    term.send(b'\x08 \x08')
                continue
            if 32 <= ord(ch) <= 126 and len(buf) < max_len:
                buf.append(ch)
                term.send(ch)

    def _preview(self, term: MinitelTerminal, state: "SessionState", visible: list, cursor: int):
        self._clear_right(term)
        if not visible:
            return
        item = visible[cursor]

        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(term.seq_smso())
        term.send(f" {item.label} ".ljust(RIGHT_W))
        term.send(term.seq_rmso())

        from .actions import TextPage

        if isinstance(item.action, TextPage) and os.path.isfile(item.action.path):
            try:
                with open(item.action.path, 'r', encoding='latin-1', errors='ignore') as f:
                    lines = f.read().splitlines()
                for i, ln in enumerate(lines[:CONTENT_H - 1]):
                    row = CONTENT_TOP + 1 + i
                    if row > CONTENT_BOTTOM:
                        break
                    term.send(term.seq_cup(row, RIGHT_COL))
                    term.send(MinitelTerminal.safe_line(ln)[:RIGHT_W])
            except Exception:
                pass

        elif isinstance(item.action, SplitMenu):
            # Afficher les items du sous-dossier en aperçu
            sub_visible = [i for i in item.action._items if i.is_visible(state)]
            for i, sub in enumerate(sub_visible[:CONTENT_H - 1]):
                row = CONTENT_TOP + 1 + i
                if row > CONTENT_BOTTOM:
                    break
                term.send(term.seq_cup(row, RIGHT_COL))
                term.send(f"  {sub.label}"[:RIGHT_W])

    def _render_frame(self, term: MinitelTerminal):
        term.clear()
        term.send(term.seq_cup(1, 1))
        term.send(term.seq_smso())
        term.send(f" {self.header} ".ljust(COLS))
        term.send(term.seq_rmso())

        term.send(term.seq_cup(3, 2))
        term.send(self.folder_label[:LEFT_W - 2])

        for r in range(3, LINES - 1):
            term.send(term.seq_cup(r, SEP_COL))
            term.send("|")

        term.send(term.seq_cup(4, 1))
        term.send("-" * LEFT_W)
        term.send("+")
        term.send("-" * RIGHT_W)

        term.send(term.seq_cup(LINES - 1, 1))
        term.send("-" * COLS)

        term.send(term.seq_cup(LINES, 1))
        term.send(self.footer[:COLS])

    def _render_list(self, term: MinitelTerminal, visible: list, cursor: int):
        for i, item in enumerate(visible[:CONTENT_H]):
            row = CONTENT_TOP + i
            label = item.label[:LEFT_W - 3]
            term.send(term.seq_cup(row, 1))
            if i == cursor:
                term.send(term.seq_smso())
                term.send(f" {label}".ljust(LEFT_W))
                term.send(term.seq_rmso())
            else:
                term.send(f"  {label}".ljust(LEFT_W))

    def _visible(self, state: "SessionState") -> list[SplitItem]:
        return [item for item in self._items if item.is_visible(state)]

    def _read_key(self, term: MinitelTerminal) -> bytes:
        b = term.read(1)
        if not b:
            return b''
        if b == b'\x1b':
            b2 = term.read(1)
            if b2 == b'[':
                b3 = term.read(1)
                return b'\x1b[' + b3
            return b'\x1b'
        return b


class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *_): pass
