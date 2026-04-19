# -*- coding: utf-8 -*-
"""
engine/menusplit.py
===================
Menu deux colonnes style Alien Isolation / SEVASTOLINK.

Disposition :
  Colonne gauche (LEFT_W)  : liste des dossiers/items (navigation au clavier)
  Colonne droite           : aperçu ou contenu de l'item sélectionné
  Ligne de footer          : aide contextuelle

Ce module expose :
  SplitMenu  : menu deux colonnes avec navigation flèches
  SplitItem  : un item dans un SplitMenu
  AudioItem  : item spécial pour la lecture de fichiers audio

Personnalisation
-----------------
Toutes les options de layout, sons, touches et textes de navigation
sont configurables à l'instanciation de SplitMenu.

Voir la docstring de SplitMenu pour la liste complète des paramètres.
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


# ---------------------------------------------------------------------------
# Constantes de layout (modifiables par héritage si besoin)
# ---------------------------------------------------------------------------

LEFT_W  = 20          # largeur de la colonne gauche (dossiers/liste)
SEP_COL = LEFT_W + 1  # colonne du séparateur vertical "|"
RIGHT_COL = LEFT_W + 2  # première colonne du panneau droit
RIGHT_W = COLS - RIGHT_COL + 1  # largeur du panneau droit

CONTENT_TOP    = 5       # première ligne de la zone de contenu
CONTENT_BOTTOM = LINES - 2  # dernière ligne de la zone de contenu
CONTENT_H      = CONTENT_BOTTOM - CONTENT_TOP + 1

# Codes de séquences flèches (ANSI)
SEQ_UP    = b'\x1b[A'
SEQ_DOWN  = b'\x1b[B'
SEQ_RIGHT = b'\x1b[C'
SEQ_LEFT  = b'\x1b[D'


# ---------------------------------------------------------------------------
# AudioItem : item de lecture audio
# ---------------------------------------------------------------------------

class AudioItem:
    """
    Item spécial pour la lecture d'un fichier audio depuis un SplitMenu.

    Paramètres
    ----------
    path        : chemin du fichier audio (wav, mp3, ogg selon les outils dispo)
    description : texte affiché dans le panneau droit pendant la lecture
    volume      : volume de lecture (0.0 à 1.0+, défaut 1.0)

    Exemple
    -------
        AudioItem(
            path        = "assets/sounds/log_marlowe.wav",
            description = "Journal personnel — D. Marlowe",
            volume      = 0.8,
        )
    """

    def __init__(self, path: str, description: str = None, volume: float = 1.0):
        self.path        = path
        self.description = description or os.path.basename(path)
        self.volume      = volume


# ---------------------------------------------------------------------------
# SplitItem : un item dans un SplitMenu
# ---------------------------------------------------------------------------

class SplitItem:
    """
    Un item dans un SplitMenu.

    Paramètres
    ----------
    label     : texte affiché dans la colonne gauche
    action    : SplitMenu (sous-dossier), TextPage, LLMTerminal,
                AudioItem, ou callable(term, state)
    condition : callable(state) -> bool — masque l'item si False
    """

    def __init__(self, label: str, action, condition: Callable = None):
        self.label     = label
        self.action    = action
        self.condition = condition

    def is_visible(self, state: "SessionState") -> bool:
        """Retourne True si l'item doit être affiché."""
        if self.condition is None:
            return True
        try:
            return bool(self.condition(state))
        except Exception:
            return False


# ---------------------------------------------------------------------------
# SplitMenu
# ---------------------------------------------------------------------------

class SplitMenu:
    """
    Menu deux colonnes style terminal Alien Isolation.

    Navigation
    ----------
    - Flèche haut/bas  : déplace le curseur dans la liste de gauche
    - Flèche droite / Entrée : ouvre l'item sélectionné (panneau droit)
    - Flèche gauche    : retour au dossier parent (ou quitte si racine)
    - exit_key         : touche de sortie rapide (défaut "Q")

    Paramètres de personnalisation
    --------------------------------
    header         : texte de la barre de titre principale (vidéo inverse)
    folder_label   : étiquette au-dessus de la liste gauche (ex: "DOSSIERS")
    exit_key       : touche de sortie rapide (défaut "Q")
    footer         : texte de footer par défaut (rempli automatiquement si None)
    typing_sound   : son joué pendant l'affichage des items (str ou Sound)
    response_delay : pause entre les lignes d'un TextPage ouvert (défaut 0.12s)

    Touches de navigation (personnalisables)
    -----------------------------------------
    key_up    : touche haut (défaut : flèche haut ANSI)
    key_down  : touche bas (défaut : flèche bas ANSI)
    key_open  : touche ouvrir (défaut : flèche droite ANSI)
    key_back  : touche retour (défaut : flèche gauche ANSI)
    key_enter : touche confirmer (défaut : Entrée \\r)

    Textes de navigation (personnalisables)
    ----------------------------------------
    nav_navigate : label pour "naviguer" dans le footer
    nav_open     : label pour "ouvrir"
    nav_back     : label pour "retour"
    nav_play     : label pour "jouer" (AudioItem)
    nav_quit     : label pour "quitter"

    Exemple
    -------
        terminal = SplitMenu(
            header        = "SEVASTOLINK TERMINAL v2.1",
            folder_label  = "FICHIERS",
            exit_key      = "Q",
            typing_sound  = Sound("assets/sounds/typing.wav", volume=0.3),
            response_delay = 0.08,
            nav_navigate  = "[HAUT/BAS] NAVIGUER",
            nav_open      = "[DROITE] OUVRIR",
            nav_back      = "[GAUCHE] RETOUR",
            nav_quit      = "[Q] QUITTER",
        )
        terminal.add_item("DOSSIER PERSO", action=perso_folder)
        terminal.add_item("A.P.O.L.L.O",  action=apollo,
                          condition=lambda s: s.get("apollo_unlocked", True))
    """

    def __init__(
        self,
        header:          str   = "TERMINAL",
        folder_label:    str   = "FOLDERS",
        exit_key:        str   = "Q",
        footer:          str   = None,
        typing_sound                 = None,
        response_delay:  float = 0.12,
        # Touches de navigation
        key_up:    bytes = SEQ_UP,
        key_down:  bytes = SEQ_DOWN,
        key_open:  bytes = SEQ_RIGHT,
        key_back:  bytes = SEQ_LEFT,
        key_enter: bytes = b'\r',
        # Textes de navigation dans le footer
        nav_navigate: str = "[HAUT/BAS] NAVIGUER",
        nav_open:     str = "[DROITE] OUVRIR",
        nav_back:     str = "[GAUCHE] RETOUR",
        nav_play:     str = "[ENTREE] JOUER",
        nav_quit:     str = None,
        # Textes d'état (panneaux droit, audio, erreurs)
        nav_next_label:   str = "SUITE",
        nav_play_status:  str = "[ LECTURE EN COURS... ]",
        nav_play_done:    str = "[ LECTURE TERMINEE    ]",
        nav_play_hint:    str = "[ Appuyer ENTREE pour lire ]",
        nav_error_file:   str = "[ERREUR: fichier introuvable]",
        nav_file_missing: str = "[Fichier introuvable]",
    ):
        self.header         = header
        self.folder_label   = folder_label
        self.exit_key       = exit_key.upper()
        self.typing_sound   = typing_sound
        self.response_delay = response_delay
        # Touches
        self.key_up    = key_up
        self.key_down  = key_down
        self.key_open  = key_open
        self.key_back  = key_back
        self.key_enter = key_enter
        # Textes de navigation
        self.nav_navigate = nav_navigate
        self.nav_open     = nav_open
        self.nav_back     = nav_back
        self.nav_play     = nav_play
        self.nav_quit     = nav_quit or f"[{exit_key}] QUITTER"
        # Textes d'état
        self.nav_next_label   = nav_next_label
        self.nav_play_status  = nav_play_status
        self.nav_play_done    = nav_play_done
        self.nav_play_hint    = nav_play_hint
        self.nav_error_file   = nav_error_file
        self.nav_file_missing = nav_file_missing

        # Footer par défaut construit à partir des labels de navigation
        self.footer = footer or (
            f"{self.nav_navigate}  {self.nav_open}  {self.nav_quit}"
        )

        self._items: list[SplitItem] = []
        self._events: list = []

    def on_state(
        self,
        key:   str,
        value         = None,
        sound         = None,
        alert         = None,
        callback      = None,
    ) -> "SplitMenu":
        """
        Déclenche une alerte plein écran et/ou un callback quand une clé d'état
        prend la valeur donnée (ou change si value=None).

        Paramètres
        ----------
        key      : clé de l'état surveillée (ex: \"self_destruct\")
        value    : valeur déclenchante (ex: True). None = tout changement.
        sound    : son joué (str ou Sound)
        alert    : FullscreenAlert à afficher
        callback : fonction(term, state) appelée en supplément

        Exemple
        -------
            sevastolink.on_state(
                \"self_destruct\",
                value = True,
                sound = Sound(\"assets/sounds/horn.wav\", volume=1.0),
                alert = FullscreenAlert(
                    text        = \"AUTODESTRUCTION INITIÉE\",
                    dismissible = False,
                ),
            )
        """
        self._events.append({
            "key": key, "value": value,
            "sound": sound, "alert": alert, "callback": callback,
        })
        return self

    def add_item(
        self,
        label:     str,
        action,
        condition: Callable = None,
    ) -> "SplitMenu":
        """
        Ajoute un item à la liste.

        Paramètres
        ----------
        label     : texte affiché dans la colonne gauche
        action    : SplitMenu, TextPage, LLMTerminal, AudioItem, ou callable
        condition : callable(state) -> bool — masque l'item si False

        Retourne self pour le chaînage fluent.

        Exemple
        -------
            menu.add_item("RAPPORT", action=TextPage("rapport.txt"))
            menu.add_item(
                "APOLLO",
                action    = apollo_terminal,
                condition = lambda s: s.get("apollo_unlocked", False),
            )
        """
        self._items.append(SplitItem(label, action, condition))
        return self

    # ------------------------------------------------------------------
    # Watchers d'état
    # ------------------------------------------------------------------

    def _register_watchers(self, term: MinitelTerminal, state: "SessionState"):
        """Branche chaque événement on_state sur le système de watchers."""
        from .audio import play_once
        for ev in self._events:
            def make_handler(e):
                def handler(new_value):
                    trigger = e["value"]
                    if trigger is not None and new_value != trigger:
                        return
                    # Empile l'alerte pour déclenchement différé après la réponse LLM
                    state._pending_alerts.append(e)
                return handler
            state.watch(ev["key"], make_handler(ev))

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """Lance la boucle interactive du SplitMenu."""
        self._register_watchers(term, state)
        cursor  = 0
        self._render_frame(term)
        visible = self._visible(state)
        if not visible:
            return
        self._render_list(term, visible, cursor)
        self._preview(term, state, visible, cursor)

        while True:
            seq = self._read_key(term)

            # Quitter
            if seq in (self.exit_key.encode(), self.exit_key.lower().encode()):
                term.beep()
                return

            # Navigation haut
            elif seq == self.key_up:
                if cursor > 0:
                    cursor -= 1
                    self._render_list(term, visible, cursor)
                    self._preview(term, state, visible, cursor)

            # Navigation bas
            elif seq == self.key_down:
                if cursor < len(visible) - 1:
                    cursor += 1
                    self._render_list(term, visible, cursor)
                    self._preview(term, state, visible, cursor)

            # Ouvrir (flèche droite)
            elif seq == self.key_open:
                self._open_item(term, state, visible, cursor)
                # Restaurer le footer principal au retour
                self._restore_footer(term)

            # Ouvrir (Entrée)
            elif seq in (self.key_enter, b'\n'):
                term.beep()
                self._open_item(term, state, visible, cursor)
                # Pour les actions non-split, re-render complet
                item = visible[cursor]
                from .actions import TextPage, LLMTerminal
                if not isinstance(item.action, (SplitMenu, TextPage, LLMTerminal, AudioItem)):
                    self._render_frame(term)
                    visible = self._visible(state)
                    if cursor >= len(visible):
                        cursor = max(0, len(visible) - 1)
                    self._render_list(term, visible, cursor)
                    self._preview(term, state, visible, cursor)
                else:
                    self._restore_footer(term)

    def _open_item(self, term: MinitelTerminal, state: "SessionState",
                   visible: list, cursor: int):
        """Dispatche vers la méthode de rendu appropriée selon le type d'action."""
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
        else:
            if callable(item.action) and not hasattr(item.action, "run"):
                item.action(term, state)
            else:
                item.action.run(term, state)

    def _restore_footer(self, term: MinitelTerminal):
        """Restaure le footer principal après retour d'un sous-module."""
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(self.footer[: COLS])

    # ------------------------------------------------------------------
    # Affichage TextPage dans le panneau droit
    # ------------------------------------------------------------------

    def _run_text_right(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        """Affiche un TextPage dans le panneau droit du SplitMenu."""
        from .actions import TextPage
        action: TextPage = item.action

        if not os.path.isfile(action.path):
            self._clear_right(term)
            term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
            term.send(self.nav_file_missing)
            self._set_footer(term, f"{self.nav_back}")
            self._wait_back(term)
            return

        with open(action.path, "r", encoding="latin-1", errors="ignore") as f:
            raw_lines = f.read().splitlines()

        lines  = [MinitelTerminal.safe_line(ln).expandtabs(8) for ln in raw_lines]
        idx    = 0
        window = CONTENT_H - 1  # -1 pour le titre de l'item

        while True:
            self._clear_right(term)
            # Titre de l'item en vidéo inverse
            term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
            term.send(term.seq_smso())
            term.send(f" {item.label} ".ljust(RIGHT_W))
            term.send(term.seq_rmso())

            # Contenu
            with LoopPlayer(action.typing_sound) if action.typing_sound else _NullCtx():
                written = 0
                while idx < len(lines) and written < window:
                    row = CONTENT_TOP + 1 + written
                    ln  = lines[idx][: RIGHT_W]
                    term.send(term.seq_cup(row, RIGHT_COL))
                    term.send(ln)
                    time.sleep(action.scroll_delay)
                    idx     += 1
                    written += 1

            if idx >= len(lines):
                self._set_footer(term, f"{self.nav_back}")
                self._wait_back(term)
                return
            else:
                self._set_footer(term, f"[ENTREE] {self.nav_next_label}  {self.nav_back}")
                seq = self._read_key(term)
                if seq == self.key_back:
                    return

    def _fire_pending_alerts(self, term: MinitelTerminal, state: "SessionState", delay: float = 10.0):
        """
        Déclenche les alertes en attente après `delay` secondes.
        Appelé dans un thread depuis _run_llm_right.
        """
        import threading
        from .audio import play_once

        alerts = state._pending_alerts[:]
        state._pending_alerts.clear()
        if not alerts:
            return

        def _delayed():
            time.sleep(delay)
            for e in alerts:
                if e["sound"]:
                    play_once(e["sound"])
                if e["alert"]:
                    e["alert"].fire(term, state)
                    if e["alert"].dismissible:
                        # Redessiner le SplitMenu au retour
                        self._render_frame(term)
                        visible = self._visible(state)
                        self._render_list(term, visible, 0)
                        self._preview(term, state, visible, 0)
                if e["callback"]:
                    try:
                        e["callback"](term, state)
                    except Exception as ex:
                        print(f"[on_state] callback error: {ex}")

        threading.Thread(target=_delayed, daemon=True).start()

    # ------------------------------------------------------------------
    # Affichage LLMTerminal dans le panneau droit
    # ------------------------------------------------------------------

    def _run_llm_right(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        """Interface de chat LLM dans le panneau droit du SplitMenu."""
        from .actions import LLMTerminal
        action: LLMTerminal = item.action

        llm = action._get_llm()
        llm.reset_history()

        self._clear_right(term)
        # Titre
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(term.seq_smso())
        term.send(f" {item.label} ".ljust(RIGHT_W))
        term.send(term.seq_rmso())

        resp_top    = CONTENT_TOP + 1
        resp_bottom = LINES - 2

        self._set_footer(term, f"[{action.input_prompt}]> ")

        while True:
            user_input = self._read_line_right(term, check_back=True)

            if user_input is None:
                # Flèche gauche : retour
                return

            if not user_input.strip():
                self._set_footer(term, f"[{action.input_prompt}]> ")
                continue

            # Affiche [YOU]
            self._clear_right_content(term, resp_top, resp_bottom)
            term.send(term.seq_cup(resp_top, RIGHT_COL))
            term.send(term.seq_smso())
            term.send(f"{action.label_you} ")
            term.send(term.seq_rmso())
            you = MinitelTerminal.safe_line(user_input)[: RIGHT_W - 6]
            term.send(you)

            # Indicateur d'attente
            term.send(term.seq_cup(resp_top + 2, RIGHT_COL))
            term.send(term.seq_smso())
            term.send(f"[{action.name}]"[: RIGHT_W])
            term.send(term.seq_rmso())
            term.send(term.seq_cup(resp_top + 3, RIGHT_COL))
            term.send(action.label_thinking[: RIGHT_W])

            # Appel LLM
            with LoopPlayer(action.sounds.get("thinking")) if action.sounds.get("thinking") else _NullCtx():
                try:
                    response = action._get_llm().ask(user_input, state)
                except Exception as e:
                    response = f"{action.error_prefix}: {e}"

            # Affiche la réponse
            self._clear_right_content(term, resp_top + 3, resp_bottom)
            lines = []
            for raw in response.splitlines():
                raw = MinitelTerminal.safe_line(raw)
                while len(raw) > RIGHT_W:
                    lines.append(raw[: RIGHT_W])
                    raw = raw[RIGHT_W:]
                lines.append(raw)

            window = resp_bottom - (resp_top + 3) + 1
            with LoopPlayer(action.sounds.get("typing")) if action.sounds.get("typing") else _NullCtx():
                for i, ln in enumerate(lines[: window]):
                    term.send(term.seq_cup(resp_top + 3 + i, RIGHT_COL))
                    term.send(ln)
                    time.sleep(action.response_delay)

            # Déclencher les alertes en attente 10s après la réponse
            if state._pending_alerts:
                self._fire_pending_alerts(term, state, delay=10.0)

            self._set_footer(term, f"[{action.input_prompt}]> ")

    # ------------------------------------------------------------------
    # Sous-dossier (SplitMenu imbriqué)
    # ------------------------------------------------------------------

    def _run_subfolder(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        """Navigue dans un sous-SplitMenu affiché dans le panneau droit."""
        subfolder: SplitMenu = item.action
        visible = [i for i in subfolder._items if i.is_visible(state)]
        if not visible:
            return

        cursor = 0
        # La preview a déjà dessiné le panneau droit — on retire juste l'inverse
        # du titre et on met le premier item en surbrillance, sans tout redessiner.
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(f" {item.label} ".ljust(RIGHT_W))
        self._update_subfolder_cursor(term, visible, -1, cursor)
        self._set_footer(term, self._subfolder_footer(subfolder, visible, cursor))

        while True:
            seq = self._read_key(term)

            if seq == self.key_back:
                return

            elif seq == self.key_up:
                if cursor > 0:
                    old    = cursor
                    cursor -= 1
                    self._update_subfolder_cursor(term, visible, old, cursor)

            elif seq == self.key_down:
                if cursor < len(visible) - 1:
                    old    = cursor
                    cursor += 1
                    self._update_subfolder_cursor(term, visible, old, cursor)

            elif seq in (self.key_enter, b'\n'):
                term.beep()
                sub_item = visible[cursor]
                from .actions import TextPage, LLMTerminal
                if isinstance(sub_item.action, AudioItem):
                    self._run_audio_right(term, state, sub_item)
                    self._render_subfolder_right(term, item.label, visible, cursor)
                    self._set_footer(term, self._subfolder_footer(subfolder, visible, cursor))
                elif isinstance(sub_item.action, TextPage):
                    self._run_text_right(term, state, sub_item)
                    self._render_subfolder_right(term, item.label, visible, cursor)
                    self._set_footer(term, self._subfolder_footer(subfolder, visible, cursor))
                elif isinstance(sub_item.action, LLMTerminal):
                    self._run_llm_right(term, state, sub_item)
                    self._render_subfolder_right(term, item.label, visible, cursor)
                    self._set_footer(term, self._subfolder_footer(subfolder, visible, cursor))
                else:
                    if callable(sub_item.action) and not hasattr(sub_item.action, "run"):
                        sub_item.action(term, state)
                    else:
                        sub_item.action.run(term, state)
                    self._render_subfolder_right(term, item.label, visible, cursor)
                    self._set_footer(term, self._subfolder_footer(subfolder, visible, cursor))

    def _render_subfolder_right(self, term: MinitelTerminal, folder_label: str,
                                  visible: list, cursor: int):
        """Dessine la liste d'un sous-dossier dans le panneau droit."""
        self._clear_right(term)
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(f" {folder_label} ".ljust(RIGHT_W))

        for i, sub_item in enumerate(visible[: CONTENT_H - 1]):
            row = CONTENT_TOP + 1 + i
            if row > CONTENT_BOTTOM:
                break
            label = sub_item.label[: RIGHT_W - 3]
            term.send(term.seq_cup(row, RIGHT_COL))
            if i == cursor:
                term.send(term.seq_smso())
                term.send(f" {label}".ljust(RIGHT_W))
                term.send(term.seq_rmso())
            else:
                term.send(f"  {label}".ljust(RIGHT_W))

    def _subfolder_footer(self, subfolder: "SplitMenu", visible: list, cursor: int) -> str:
        """Retourne le footer adapté au type de l'item courant dans le sous-dossier."""
        from .actions import TextPage, LLMTerminal
        item = visible[cursor]
        if isinstance(item.action, AudioItem):
            return f"{subfolder.nav_navigate}  {subfolder.nav_play}  {self.nav_back}"
        return f"{subfolder.nav_navigate}  {subfolder.nav_open}  {self.nav_back}"

    def _update_subfolder_cursor(self, term: MinitelTerminal, visible: list,
                                   old: int, new: int):
        """Redessine seulement les deux lignes du curseur (ancienne et nouvelle position)."""
        for i in (old, new):
            if i < 0 or i >= len(visible):
                continue
            row = CONTENT_TOP + 1 + i
            if row > CONTENT_BOTTOM:
                continue
            label = visible[i].label[: RIGHT_W - 3]
            term.send(term.seq_cup(row, RIGHT_COL))
            if i == new:
                term.send(term.seq_smso())
                term.send(f" {label}".ljust(RIGHT_W))
                term.send(term.seq_rmso())
            else:
                term.send(f"  {label}".ljust(RIGHT_W))

    # ------------------------------------------------------------------
    # Lecture audio dans le panneau droit
    # ------------------------------------------------------------------

    def _run_audio_right(self, term: MinitelTerminal, state: "SessionState", item: SplitItem):
        """Lance la lecture audio et affiche les contrôles dans le panneau droit."""
        from .audio import _build_cmd
        action: AudioItem = item.action

        self._clear_right(term)
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(term.seq_smso())
        term.send(f" {item.label} ".ljust(RIGHT_W))
        term.send(term.seq_rmso())

        term.send(term.seq_cup(CONTENT_TOP + 2, RIGHT_COL))
        term.send(action.description[: RIGHT_W])

        if not os.path.isfile(action.path):
            term.send(term.seq_cup(CONTENT_TOP + 4, RIGHT_COL))
            term.send(self.nav_error_file)
            self._set_footer(term, f"{self.nav_back}")
            self._wait_back(term)
            return

        term.send(term.seq_cup(CONTENT_TOP + 4, RIGHT_COL))
        term.send(self.nav_play_status)
        self._set_footer(term, f"{self.nav_back}")

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
            if seq == self.key_back:
                stop_event.set()
                t.join(timeout=0.5)
                return

        t.join(timeout=0.5)
        term.send(term.seq_cup(CONTENT_TOP + 4, RIGHT_COL))
        term.send(self.nav_play_done)
        self._set_footer(term, f"{self.nav_back}")
        self._wait_back(term)

    # ------------------------------------------------------------------
    # Helpers de rendu
    # ------------------------------------------------------------------

    def _clear_right(self, term: MinitelTerminal):
        """Efface tout le panneau droit."""
        for r in range(CONTENT_TOP, LINES - 1):
            term.send(term.seq_cup(r, RIGHT_COL))
            term.send(term.seq_el())

    def _clear_right_content(self, term: MinitelTerminal, top: int, bottom: int):
        """Efface une sous-zone du panneau droit."""
        for r in range(top, bottom + 1):
            term.send(term.seq_cup(r, RIGHT_COL))
            term.send(term.seq_el())

    def _set_footer(self, term: MinitelTerminal, text: str):
        """Affiche le texte de footer sur la dernière ligne."""
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(text[: COLS])

    def _wait_back(self, term: MinitelTerminal):
        """Attend que l'utilisateur appuie sur la touche retour (ou Entrée)."""
        while True:
            seq = self._read_key(term)
            if seq in (self.key_back, self.key_enter, b'\n', b'q', b'Q'):
                return

    def _read_line_right(self, term: MinitelTerminal, check_back: bool = False):
        """
        Lit une ligne de saisie dans le footer du panneau droit.

        Si check_back=True et que l'utilisateur appuie sur la flèche gauche,
        retourne None pour signaler un retour au parent.
        """
        buf     = []
        max_len = RIGHT_W - 20
        while True:
            b = term.read(1)
            if not b:
                continue
            if b == b'\x1b':
                b2 = term.read(1)
                if b2 == b'[':
                    b3 = term.read(1)
                    if check_back and b3 == b'D':
                        return None  # flèche gauche → retour
                continue
            ch = b.decode("latin-1", errors="ignore")
            if ch in ("\r", "\n"):
                return "".join(buf)
            if ord(ch) in (8, 127):
                if buf:
                    buf.pop()
                    term.send(b'\x08 \x08')
                continue
            if 32 <= ord(ch) <= 126 and len(buf) < max_len:
                buf.append(ch)
                term.send(ch)

    def _preview(self, term: MinitelTerminal, state: "SessionState",
                 visible: list, cursor: int):
        """
        Affiche un aperçu de l'item sélectionné dans le panneau droit.
        - TextPage : affiche les premières lignes du fichier
        - SplitMenu : liste les items du sous-dossier
        - Autres : affiche juste le nom en titre
        """
        self._clear_right(term)
        if not visible:
            return
        item = visible[cursor]

        # Titre de l'aperçu
        term.send(term.seq_cup(CONTENT_TOP, RIGHT_COL))
        term.send(term.seq_smso())
        term.send(f" {item.label} ".ljust(RIGHT_W))
        term.send(term.seq_rmso())

        from .actions import TextPage

        if isinstance(item.action, TextPage) and os.path.isfile(item.action.path):
            try:
                with open(item.action.path, "r", encoding="latin-1", errors="ignore") as f:
                    lines = f.read().splitlines()
                for i, ln in enumerate(lines[: CONTENT_H - 1]):
                    row = CONTENT_TOP + 1 + i
                    if row > CONTENT_BOTTOM:
                        break
                    term.send(term.seq_cup(row, RIGHT_COL))
                    term.send(MinitelTerminal.safe_line(ln)[: RIGHT_W])
            except Exception:
                pass

        elif isinstance(item.action, SplitMenu):
            # Aperçu : liste les items du sous-dossier
            sub_visible = [i for i in item.action._items if i.is_visible(state)]
            for i, sub in enumerate(sub_visible[: CONTENT_H - 1]):
                row = CONTENT_TOP + 1 + i
                if row > CONTENT_BOTTOM:
                    break
                term.send(term.seq_cup(row, RIGHT_COL))
                term.send(f"  {sub.label}"[: RIGHT_W])

        elif isinstance(item.action, AudioItem):
            # Aperçu audio
            term.send(term.seq_cup(CONTENT_TOP + 2, RIGHT_COL))
            term.send(item.action.description[: RIGHT_W])
            term.send(term.seq_cup(CONTENT_TOP + 4, RIGHT_COL))
            term.send(self.nav_play_hint)

    def _render_frame(self, term: MinitelTerminal):
        """Dessine le cadre fixe du SplitMenu : header, séparateur, footer."""
        term.clear()

        # Header
        term.send(term.seq_cup(1, 1))
        term.send(term.seq_smso())
        term.send(f" {self.header} ".ljust(COLS))
        term.send(term.seq_rmso())

        # Étiquette de la colonne gauche
        term.send(term.seq_cup(3, 2))
        term.send(self.folder_label[: LEFT_W - 2])

        # Séparateur vertical
        for r in range(3, LINES - 1):
            term.send(term.seq_cup(r, SEP_COL))
            term.send("|")

        # Séparateur horizontal sous l'étiquette
        term.send(term.seq_cup(4, 1))
        term.send("-" * LEFT_W)
        term.send("+")
        term.send("-" * RIGHT_W)

        # Séparateur horizontal avant le footer
        term.send(term.seq_cup(LINES - 1, 1))
        term.send("-" * COLS)

        # Footer
        term.send(term.seq_cup(LINES, 1))
        term.send(self.footer[: COLS])

    def _render_list(self, term: MinitelTerminal, visible: list, cursor: int):
        """Dessine la liste des items dans la colonne gauche."""
        for i, item in enumerate(visible[: CONTENT_H]):
            row   = CONTENT_TOP + i
            label = item.label[: LEFT_W - 3]
            term.send(term.seq_cup(row, 1))
            if i == cursor:
                term.send(term.seq_smso())
                term.send(f" {label}".ljust(LEFT_W))
                term.send(term.seq_rmso())
            else:
                term.send(f"  {label}".ljust(LEFT_W))

    def _visible(self, state: "SessionState") -> list[SplitItem]:
        """Retourne la liste des items visibles (condition satisfaite)."""
        return [item for item in self._items if item.is_visible(state)]

    def _read_key(self, term: MinitelTerminal) -> bytes:
        """
        Lit une touche ou séquence d'échappement ANSI.
        Retourne bytes : la touche simple ou la séquence complète (ex: b'\\x1b[A').
        """
        b = term.read(1)
        if not b:
            return b""
        if b == b'\x1b':
            b2 = term.read(1)
            if b2 == b'[':
                b3 = term.read(1)
                return b'\x1b[' + b3
            return b'\x1b'
        return b


# ---------------------------------------------------------------------------
# Null context manager
# ---------------------------------------------------------------------------

class _NullCtx:
    """Context manager no-op pour les sons optionnels."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
