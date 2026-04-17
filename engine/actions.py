# -*- coding: utf-8 -*-
"""
engine/actions.py
=================
Briques d'action pour les menus :

  Boot          : séquence de démarrage (art ASCII, logo, barre de chargement)
  TextPage      : affichage paginé d'un fichier texte
  LLMTerminal   : interface de chat LLM (OpenAI / Anthropic / Ollama)
  CallbackAction: action Python arbitraire (lambda ou fonction)

Chaque action expose une méthode run(term, state) appelée par le moteur
de menu quand l'utilisateur sélectionne l'entrée correspondante.

Philosophie de personnalisation
--------------------------------
Toutes les options de timing, sons, textes et touches sont configurables
comme arguments nommés à l'instanciation. Les valeurs par défaut sont
raisonnables pour un Minitel à 4800 baud.
"""

import os
import time
from typing import TYPE_CHECKING, Callable

from .audio    import LoopPlayer, play_once, play_async, Sound
from .terminal import MinitelTerminal, COLS, LINES

if TYPE_CHECKING:
    from .state import SessionState
    from .menu  import Menu


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _read_lines(path: str) -> list[str]:
    """Lit un fichier texte en latin-1 et retourne la liste des lignes."""
    with open(path, "r", encoding="latin-1", errors="ignore") as f:
        return f.read().splitlines()


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

class Boot:
    """
    Séquence de démarrage jouée une fois au lancement de la campagne.

    Déroulement
    -----------
    1. Affiche l'art ASCII (`art`) avec le son de boot en fond
    2. Affiche le prompt de confirmation (ex: "BOOT ? (Y/N)")
    3. Si confirmé : affiche le logo (`logo`) quelques secondes
    4. Défile le texte de boot (`scroll_text`)
    5. Affiche la barre de chargement
    6. Joue le son final et retourne au moteur

    Paramètres de personnalisation
    --------------------------------
    art                   : fichier texte contenant l'art ASCII d'accueil
    scroll_text           : fichier texte défilant après confirmation (logs de boot, etc.)
    logo                  : fichier texte affiché en plein écran après confirmation
    logo_display_duration : durée d'affichage du logo en secondes (défaut 3.0)
    boot_sound            : son joué en fond pendant l'affichage de l'art ASCII
    beep_sound            : son joué immédiatement après confirmation
    typing_sound          : son joué en boucle pendant le défilement du scroll_text
    loading_sound         : son joué en boucle pendant la barre de chargement
    final_sound           : son joué une fois à la fin du boot
    loading_duration      : durée de la barre de chargement en secondes (défaut 5)
    scroll_delay          : pause entre chaque ligne du scroll_text en secondes (défaut 0.10)
                            Réduire pour un défilement plus rapide.
    prompt                : texte du prompt de confirmation (défaut "BOOT ? (Y/N) : ")
    confirm_key           : touche attendue pour confirmer (défaut "Y", insensible casse)
    cancel_key            : touche pour annuler / éteindre (défaut "N")

    Exemple
    -------
        boot = Boot(
            art              = "assets/art.txt",
            scroll_text      = "assets/boot.txt",
            logo             = "assets/logo.txt",
            boot_sound       = Sound("assets/sounds/boot.wav", volume=0.8),
            beep_sound       = "assets/sounds/beep.wav",
            typing_sound     = Sound("assets/sounds/typing.wav", volume=0.3),
            loading_sound    = "assets/sounds/hum.wav",
            final_sound      = "assets/sounds/horn.wav",
            loading_duration = 8,
            scroll_delay     = 0.08,
            prompt           = "  INITIALISER SYSTEME ? (Y/N) : ",
            confirm_key      = "Y",
        )
    """

    def __init__(
        self,
        art:                   str   = None,
        scroll_text:           str   = None,
        logo:                  str   = None,
        logo_display_duration: float = 3.0,
        boot_sound                   = None,
        beep_sound                   = None,
        typing_sound                 = None,
        loading_sound                = None,
        final_sound                  = None,
        loading_duration:      int   = 5,
        scroll_delay:          float = 0.10,
        prompt:                str   = "BOOT ? (Y/N) : ",
        confirm_key:           str   = "Y",
        cancel_key:            str   = "N",
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
        self.confirm_key           = confirm_key.upper()
        self.cancel_key            = cancel_key.upper()

    def run(self, term: MinitelTerminal, state: "SessionState") -> bool:
        """
        Exécute la séquence de boot.
        Retourne True si l'utilisateur a confirmé, False sinon.
        """
        term.clear()
        self._show_art(term)
        play_async(self.boot_sound)

        # Affiche le prompt et attend la touche de confirmation
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(self.prompt)
        ans = term.wait_key(self.confirm_key + self.cancel_key)

        if ans != self.confirm_key:
            return False

        term.clear()
        play_once(self.beep_sound)

        # 1. Logo plein écran
        if self.logo:
            self._show_logo(term)

        # 2. Défilement du texte de boot
        if self.scroll_text:
            self._scroll_file(term, self.scroll_text)

        # 3. Barre de chargement
        self._loading_bar(term)
        play_once(self.final_sound)
        return True

    def _show_art(self, term: MinitelTerminal):
        """Affiche le fichier art ASCII brut (peut contenir des séquences ESC)."""
        if not self.art or not os.path.isfile(self.art):
            return
        with open(self.art, "rb") as f:
            lines = f.read().split(b"\n")
        for r, ln in enumerate(lines[: LINES - 1], start=1):
            term.send(term.seq_cup(r, 1))
            term.send(term.seq_el())
            term.send(ln)  # bytes bruts : peut inclure séquences ESC Minitel

    def _show_logo(self, term: MinitelTerminal):
        """Affiche le fichier logo en plein écran pendant logo_display_duration secondes."""
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

    def _scroll_file(self, term: MinitelTerminal, path: str):
        """
        Défile le fichier texte ligne par ligne dans la zone (1 → LINES-1).

        scroll_delay contrôle la vitesse : 0.05 = rapide, 0.15 = lent.
        """
        if not os.path.isfile(path):
            return
        lines  = _read_lines(path)
        top    = 1
        bottom = LINES - 1
        window = bottom - top + 1

        term.clear_window(top, bottom)
        term.civis()

        with LoopPlayer(self.typing_sound) if self.typing_sound else _NullCtx():
            filled = 0
            for raw in lines:
                ln = MinitelTerminal.safe_line(raw)[: COLS]
                if filled < window:
                    # Zone pas encore pleine : écriture directe
                    term.send(term.seq_cup(top + filled, 1))
                    term.send(term.seq_el())
                    term.send(ln)
                    filled += 1
                else:
                    # Zone pleine : scroll d'une ligne vers le haut
                    term.send(term.seq_cup(top, 1))
                    term.send(term.seq_dl1())
                    term.send(term.seq_cup(bottom, 1))
                    term.send(term.seq_el())
                    term.send(ln)
                time.sleep(self.scroll_delay)

        term.cnorm()

    def _loading_bar(self, term: MinitelTerminal):
        """
        Affiche une barre de progression sur la dernière ligne.
        Durée contrôlée par loading_duration (secondes).
        """
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
        # Barre complète
        term.send(term.seq_cup(LINES, 1))
        term.send("#" * COLS)


# ---------------------------------------------------------------------------
# TextPage
# ---------------------------------------------------------------------------

class TextPage:
    """
    Affiche un fichier texte de façon paginée sur le Minitel.

    Chaque "page" occupe les lignes 4 à LINES-1 (zone de contenu).
    L'utilisateur appuie sur Entrée pour passer à la page suivante.

    Paramètres de personnalisation
    --------------------------------
    path         : chemin du fichier texte à afficher (latin-1)
    typing_sound : son joué en boucle pendant l'écriture de chaque page
                   (str ou Sound avec volume)
    scroll_delay : pause entre chaque ligne lors de l'écriture (défaut 0.12s)
                   Réduire pour un affichage plus rapide.
    header       : texte du header de la page (défaut : nom du fichier)
    footer_next  : message affiché en bas quand il y a une suite (défaut "[SUITE. ENTREE]")
    footer_end   : message affiché en bas à la fin du document (défaut "[FIN. ENTREE]")
    continue_key : touche pour passer à la page suivante (défaut : Entrée)

    Exemple
    -------
        TextPage(
            "assets/rapport.txt",
            typing_sound = Sound("assets/sounds/typing.wav", volume=0.5),
            scroll_delay = 0.08,
            header       = "RAPPORT DE SITUATION",
            footer_next  = "[PAGE SUIVANTE — APPUYER SUR ENTREE]",
            footer_end   = "[FIN DU RAPPORT — APPUYER SUR ENTREE]",
        )
    """

    def __init__(
        self,
        path:         str,
        typing_sound       = None,
        scroll_delay: float = 0.12,
        header:       str   = None,
        footer_next:  str   = "[SUITE. Appuyez ENTREE pour continuer]",
        footer_end:   str   = "[FIN. Appuyez ENTREE pour revenir]",
    ):
        self.path         = path
        self.typing_sound = typing_sound
        self.scroll_delay = scroll_delay
        self.header       = header or os.path.basename(path)
        self.footer_next  = footer_next
        self.footer_end   = footer_end

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """Affiche le fichier paginé. Retourne au menu parent à la fin."""
        if not os.path.isfile(self.path):
            term.at(LINES, 1, f"[Fichier introuvable : {self.path}]")
            term.wait_enter()
            return

        # Prépare les lignes : safe_line + expand tabs
        lines = [
            MinitelTerminal.safe_line(ln).expandtabs(8)
            for ln in _read_lines(self.path)
        ]

        top    = 4          # première ligne de contenu (après le header)
        bottom = LINES - 1  # dernière ligne de contenu (avant le footer)
        window = bottom - top + 1
        idx    = 0          # index courant dans les lignes

        while True:
            term.clear_window(top, bottom)

            # Header de la page
            term.at(1, 1, f"# - {self.header}", reverse=True)
            term.at(3, 2, "_" * (COLS - 2))
            term.send(term.seq_cup(top, 1))

            # Écriture de la page courante avec son de frappe
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
                # Dernière page
                term.at(LINES, 1, self.footer_end[: COLS - 2])
                term.wait_enter()
                return
            else:
                # Il y a une suite
                term.at(LINES, 1, self.footer_next[: COLS - 2])
                term.wait_enter()


# ---------------------------------------------------------------------------
# LLMTerminal
# ---------------------------------------------------------------------------

class LLMTerminal:
    """
    Interface de chat LLM affichée sur le Minitel.

    Affiche un header, une zone de réponse et une ligne d'invite.
    L'utilisateur tape sa question, le LLM répond, et ainsi de suite
    jusqu'à la commande exit_command.

    Paramètres de personnalisation
    --------------------------------
    name             : nom de l'IA (ex: "A.P.O.L.L.O", "MU/TH/UR 6000")
    header           : texte de la barre de titre (défaut : name)
    input_prompt     : texte précédant la zone de saisie (défaut : "[name]> ")
    prompt / prompt_file : system prompt LLM (texte direct ou fichier .txt)
    provider         : "openai" | "anthropic" | "ollama"
    model            : identifiant du modèle LLM
    api_key          : clé API (sinon lue depuis les variables d'environnement)
    base_url         : URL de base pour Ollama (défaut http://localhost:11434)
    sounds           : dictionnaire de sons :
                         "typing"   → son joué pendant l'affichage de la réponse
                         "thinking" → son joué pendant l'attente de la réponse LLM
                       Valeurs : str (path) ou Sound(path, volume=0.x)
    exit_command     : commande pour quitter le terminal (défaut "/exit")
    response_delay   : pause entre chaque ligne de réponse en secondes (défaut 0.02)
                       Augmenter pour un effet "machine à écrire" plus lent.

    Séquence de boot optionnelle du terminal LLM
    ----------------------------------------------
    boot_prompt      : texte du prompt de confirmation avant d'accéder au terminal
                       (ex: "INITIALISER A.P.O.L.L.O ? (Y/N) : ")
    boot_confirm     : touche de confirmation (défaut "Y")
    boot_logo        : fichier texte défilant après confirmation (logo de l'IA)
    boot_sound       : son joué pendant le défilement du logo de boot
    boot_scroll_delay: pause entre chaque ligne du logo de boot (défaut 0.10)

    Messages d'interface
    ---------------------
    label_you        : étiquette de l'utilisateur dans l'échange (défaut "[YOU]")
    label_thinking   : texte affiché pendant le calcul LLM (défaut "THINKING...")
    error_prefix     : préfixe des messages d'erreur (défaut "[SYSTEM ERROR]")
    footer_exit      : texte d'aide pour quitter (défaut "Tapez /exit pour quitter")

    Exemple
    -------
        apollo = LLMTerminal(
            name             = "A.P.O.L.L.O",
            header           = "# - A.P.O.L.L.O - CENTRAL ARTIFICIAL INTELLIGENCE",
            input_prompt     = "ENTER QUERY",
            prompt_file      = "assets/prompt_apollo.txt",
            provider         = "anthropic",
            model            = "claude-sonnet-4-6",
            sounds           = {
                "typing":   Sound("assets/sounds/typing.wav", volume=0.4),
                "thinking": Sound("assets/sounds/thinking.wav", volume=0.4),
            },
            exit_command     = "/exit",
            response_delay   = 0.03,
            boot_prompt      = "INITIALISER A.P.O.L.L.O ? (Y/N) : ",
            boot_confirm     = "Y",
            boot_logo        = "assets/logo-seegson.txt",
            boot_sound       = "assets/sounds/typing.wav",
            label_you        = "[YOU]",
            label_thinking   = "PROCESSING...",
        )
    """

    def __init__(
        self,
        name:              str,
        header:            str   = None,
        prompt:            str   = None,
        prompt_file:       str   = None,
        provider:          str   = "openai",
        model:             str   = "gpt-4o-mini",
        api_key:           str   = None,
        base_url:          str   = None,
        sounds:            dict  = None,
        exit_command:      str   = "/exit",
        response_delay:    float = 0.02,
        # Boot optionnel
        boot_prompt:       str   = None,
        boot_confirm:      str   = "Y",
        boot_logo:         str   = None,
        boot_sound                   = None,
        boot_scroll_delay: float = 0.10,
        # Labels d'interface
        input_prompt:      str   = None,
        label_you:         str   = "[YOU]",
        label_thinking:    str   = "THINKING...",
        error_prefix:      str   = "[SYSTEM ERROR]",
        footer_exit:       str   = None,
    ):
        self.name              = name
        self.header            = header or name
        self.exit_command      = exit_command
        self.sounds            = sounds or {}
        self.response_delay    = response_delay
        # Boot
        self.boot_prompt       = boot_prompt
        self.boot_confirm      = boot_confirm.upper()
        self.boot_logo         = boot_logo
        self.boot_sound        = boot_sound
        self.boot_scroll_delay = boot_scroll_delay
        # Labels
        self.input_prompt      = input_prompt or f"{self.name}"
        self.label_you         = label_you
        self.label_thinking    = label_thinking
        self.error_prefix      = error_prefix
        self.footer_exit       = footer_exit or f"Tapez {exit_command} pour quitter"

        # Chargement du system prompt
        if prompt_file and os.path.isfile(prompt_file):
            with open(prompt_file, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        elif prompt:
            system_prompt = prompt
        else:
            system_prompt = f"You are {name}, an onboard computer AI."

        self._provider_cfg = dict(
            provider      = provider,
            model         = model,
            system_prompt = system_prompt,
            api_key       = api_key,
            base_url      = base_url,
        )
        self._llm = None  # instancié à la première utilisation (lazy)

    def _get_llm(self):
        """Instancie le provider LLM au premier appel (lazy init)."""
        if self._llm is None:
            from .llm import make_provider
            self._llm = make_provider(**self._provider_cfg)
        return self._llm

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """Lance la session de chat LLM. Retourne quand l'utilisateur tape exit_command."""

        # --- Boot optionnel du terminal LLM ---
        if self.boot_prompt:
            term.clear()
            term.send(term.seq_cup(LINES, 1))
            term.send(self.boot_prompt)
            ans = term.wait_key(self.boot_confirm + "N")
            if ans != self.boot_confirm:
                return

        if self.boot_logo and os.path.isfile(self.boot_logo):
            self._scroll_boot_logo(term)

        # Réinitialise l'historique de conversation à chaque session
        llm = self._get_llm()
        llm.reset_history()

        self._render_header(term)
        self._render_footer(term)

        while True:
            # Lecture de la question utilisateur
            user_input = self._read_input(term)

            if user_input.strip().lower() == self.exit_command.lower():
                break

            # Affiche [YOU] + question, positionne pour la réponse
            start_row = self._display_exchange(term, user_input)

            # Indicateur d'attente + son "thinking"
            term.at(start_row, 1, self.label_thinking[: COLS - 2])
            with LoopPlayer(self.sounds.get("thinking")) if self.sounds.get("thinking") else _NullCtx():
                try:
                    response = self._get_llm().ask(user_input, state)
                except Exception as e:
                    response = f"{self.error_prefix}: {e}"

            self._display_response(term, response, start_row)
            self._render_footer(term)

    def _scroll_boot_logo(self, term: MinitelTerminal):
        """Défile le logo de boot du terminal LLM (style Alien Isolation)."""
        lines  = _read_lines(self.boot_logo)
        top    = 1
        bottom = LINES - 1
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
                time.sleep(self.boot_scroll_delay)

        term.cnorm()

    def _render_header(self, term: MinitelTerminal):
        """Redessine le header et le séparateur du terminal LLM."""
        init = term.seq_is2()
        if init:
            term.send(init)
        term.clear()

        # Ligne 1 : titre en vidéo inverse, centré
        title = f"# - {self.header} "
        col   = max(2, (COLS - len(title)) // 2 + 1)
        with LoopPlayer(self.sounds.get("typing")) if self.sounds.get("typing") else _NullCtx():
            term.at(1, col, title, reverse=True)

        # Ligne 2 : sous-titre
        term.at(2, 2, ("=" * 24).ljust(COLS - 1), reverse=True)
        term.send(term.seq_rmso())
        term.send(" ")

        # Ligne 3 : séparateur
        term.at(3, 2, "_" * (COLS - 2))

    def _render_footer(self, term: MinitelTerminal):
        """Affiche l'invite de saisie sur la dernière ligne."""
        term.send(term.seq_cup(LINES, 1))
        term.send(term.seq_el())
        term.send(f"[{self.input_prompt}]> ")

    def _read_input(self, term: MinitelTerminal) -> str:
        """Lit la saisie utilisateur depuis la ligne de footer."""
        prompt_len = len(f"[{self.input_prompt}]> ")
        return term.read_line(echo=True, maxlen=COLS - prompt_len)

    def _display_exchange(self, term: MinitelTerminal, user_input: str) -> int:
        """
        Affiche le bloc [YOU] + question dans la zone de contenu.
        Retourne le numéro de ligne où doit commencer la réponse.
        """
        top = 4
        term.clear_window(top, LINES - 2)
        term.send(term.seq_cup(top, 1))
        term.send(term.seq_nel())
        term.send(f"{self.label_you} "[: COLS])
        you_line = MinitelTerminal.safe_line(user_input)[: COLS]
        term.send(you_line)
        return top + 3  # [YOU] + question + ligne vide + réponse

    def _display_response(self, term: MinitelTerminal, text: str, start_row: int = 4):
        """
        Affiche la réponse LLM depuis start_row jusqu'à LINES-2.

        response_delay contrôle la vitesse d'affichage ligne par ligne.
        Si la réponse dépasse la zone, affiche "[SUITE. ENTREE]" et continue.
        """
        bottom = LINES - 2
        window = bottom - start_row + 1

        # Découpe en lignes respectant la largeur Minitel
        lines = []
        for raw in text.splitlines():
            raw = MinitelTerminal.safe_line(raw)
            while len(raw) > COLS:
                lines.append(raw[: COLS])
                raw = raw[COLS:]
            lines.append(raw)

        term.send(term.seq_cup(start_row, 1))
        with LoopPlayer(self.sounds.get("typing")) if self.sounds.get("typing") else _NullCtx():
            for ln in lines[: window]:
                term.send(ln)
                term.send(term.seq_nel())
                time.sleep(self.response_delay)

        # Suite si réponse trop longue
        if len(lines) > window:
            term.at(LINES - 1, 1, "[SUITE. ENTREE pour continuer]")
            term.wait_enter()
            rest = lines[window:]
            term.clear_window(4, bottom)
            term.send(term.seq_cup(4, 1))
            with LoopPlayer(self.sounds.get("typing")) if self.sounds.get("typing") else _NullCtx():
                for ln in rest[: bottom - 4 + 1]:
                    term.send(ln)
                    term.send(term.seq_nel())
                    time.sleep(self.response_delay)


# ---------------------------------------------------------------------------
# CallbackAction
# ---------------------------------------------------------------------------

class CallbackAction:
    """
    Action définie par une fonction Python arbitraire.

    La fonction reçoit (term, state) et peut faire n'importe quoi :
    modifier l'état, afficher du texte, jouer un son, etc.

    Paramètres
    ----------
    fn     : callable(term: MinitelTerminal, state: SessionState) -> None
    sound  : son joué avant d'exécuter fn (optionnel, str ou Sound)

    Exemple
    -------
        CallbackAction(
            fn    = lambda term, state: state.update({"power": True}),
            sound = "assets/sounds/click.wav",
        )

        # Avec plusieurs instructions :
        def activer_urgence(term, state):
            state.update({"urgence": True})
            term.at(12, 4, ">>> PROTOCOLE D'URGENCE ACTIVE <<<")
            term.wait_enter()

        CallbackAction(fn=activer_urgence)
    """

    def __init__(self, fn: Callable, sound=None):
        self.fn    = fn
        self.sound = sound

    def run(self, term: MinitelTerminal, state: "SessionState"):
        """Joue le son optionnel puis exécute la fonction."""
        if self.sound:
            play_once(self.sound)
        self.fn(term, state)


# ---------------------------------------------------------------------------
# Null context manager (pour les sons optionnels)
# ---------------------------------------------------------------------------

class _NullCtx:
    """Context manager no-op utilisé quand aucun son n'est configuré."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
