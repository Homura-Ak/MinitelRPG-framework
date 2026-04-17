# -*- coding: utf-8 -*-
"""
engine/terminal.py
==================
Primitives bas niveau pour le Minitel : envoi série, séquences ANSI/terminfo,
lecture clavier, rendu de texte.

Ce module expose :
  - MinitelTerminal  : driver réel (port série RS-232)
  - DebugTerminal    : driver debug (stdin/stdout, sans Minitel physique)

Toutes les constantes de mise en page (COLS, LINES, vitesse d'envoi) sont
des valeurs par défaut modifiables à l'instanciation via les arguments nommés
page_chunk et page_gap.
"""

import os
import subprocess
import time
import serial

# ---------------------------------------------------------------------------
# Constantes globales par défaut
# Ces valeurs s'appliquent si elles ne sont pas surchargées à l'instanciation.
# ---------------------------------------------------------------------------

# Taille logique de l'écran Minitel (80×24 en mode 80 colonnes)
COLS  = 80
LINES = 24

# Pacing série : envoi par blocs de PAGE_CHUNK octets avec une pause PAGE_GAP
# entre chaque bloc. Evite le débordement du buffer Minitel à 4800 baud.
# Augmenter PAGE_CHUNK ou réduire PAGE_GAP accélère l'envoi mais risque des artefacts.
PAGE_CHUNK = 32
PAGE_GAP   = 0.01  # secondes entre chaque bloc

# Nom du terminal terminfo pour les séquences de contrôle.
# Peut être surchargé via la variable d'env MINITEL_TERM ou via termname=...
TERMNAME = os.environ.get("MINITEL_TERM", "minitel1b-80")


# ---------------------------------------------------------------------------
# Helpers terminfo
# ---------------------------------------------------------------------------

def tput(name, *args, termname=None):
    """
    Appelle `tput` pour obtenir une séquence de contrôle terminfo.

    Paramètres
    ----------
    name     : nom de la capacité terminfo ("cup", "clear", "smso", ...)
    *args    : arguments numériques optionnels (ex: row-1, col-1 pour "cup")
    termname : type de terminal ; si None, utilise TERMNAME global

    Retourne bytes (vide si capacité inconnue ou tput échoue).
    """
    t   = termname or TERMNAME
    cmd = ["tput", "-T", t, name]
    if args:
        cmd += [str(a) for a in args]
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return b""


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class MinitelTerminal:
    """
    Driver Minitel : encapsule le port série et toutes les primitives d'affichage.

    Paramètres de personnalisation
    ------------------------------
    device     : chemin du port série, ex "/dev/ttyUSB0"
    baud       : débit en bauds (4800 standard Minitel)
    termname   : type de terminal terminfo (None → TERMNAME global)
    page_chunk : taille des blocs d'envoi en octets (None → PAGE_CHUNK global)
                 Augmenter pour accélérer l'affichage (risque d'artefacts).
    page_gap   : pause entre les blocs en secondes (None → PAGE_GAP global)
                 Réduire à 0.005 pour accélérer, 0.02 pour ralentir.

    Exemple
    -------
        term = MinitelTerminal("/dev/ttyUSB0", 4800, page_gap=0.008)
        term.open()
        term.clear()
        term.at(1, 1, "BONJOUR")
        term.close()
    """

    def __init__(
        self,
        device:     str,
        baud:       int,
        termname:   str   = None,
        page_chunk: int   = None,
        page_gap:   float = None,
    ):
        self.device     = device
        self.baud       = baud
        self.termname   = termname or TERMNAME
        # page_chunk / page_gap surchargent les globaux si précisés
        self.page_chunk = page_chunk if page_chunk is not None else PAGE_CHUNK
        self.page_gap   = page_gap   if page_gap   is not None else PAGE_GAP
        self._ser: serial.Serial | None = None

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def open(self):
        """Ouvre le port série (idempotent)."""
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(
            self.device,
            baudrate = self.baud,
            bytesize = serial.SEVENBITS,
            parity   = serial.PARITY_EVEN,
            stopbits = serial.STOPBITS_ONE,
            xonxoff  = True,
            rtscts   = False,
            dsrdtr   = False,
            timeout  = 0.1,
        )

    def close(self):
        """Ferme le port série."""
        if self._ser and self._ser.is_open:
            self._ser.close()

    def release(self):
        """Ferme temporairement le port pour le céder à un sous-processus."""
        self.close()

    def reclaim(self):
        """Réouvre le port après un release()."""
        self.open()

    @property
    def port(self):
        return self.device

    @property
    def baudrate(self):
        return self.baud

    # ------------------------------------------------------------------
    # Envoi série avec pacing
    # ------------------------------------------------------------------

    def send(self, data):
        """
        Envoie des données sur le port série avec pacing.

        data : str (encodé latin-1) ou bytes.
        Les données sont découpées en blocs de self.page_chunk octets,
        avec self.page_gap secondes de pause entre chaque bloc.
        """
        if isinstance(data, str):
            data = data.encode("latin-1", errors="ignore")
        for i in range(0, len(data), self.page_chunk):
            self._ser.write(data[i : i + self.page_chunk])
            self._ser.flush()
            time.sleep(self.page_gap)

    def read(self, n=1) -> bytes:
        """Lit n octets sur le port (bloquant jusqu'au timeout de 0.1s)."""
        return self._ser.read(n)

    # ------------------------------------------------------------------
    # Séquences terminfo avec fallback ANSI
    # ------------------------------------------------------------------

    def _seq(self, cap, *args, fallback=b""):
        """
        Retourne la séquence terminfo pour la capacité `cap`.
        Si tput échoue, retourne le fallback ANSI.
        """
        s = tput(cap, *args, termname=self.termname)
        return s if s else fallback

    def seq_clear(self):
        """Efface tout l'écran et positionne le curseur en (1,1)."""
        return self._seq("clear", fallback=b"\x1b[2J\x1b[H")

    def seq_cup(self, row: int, col: int):
        """Positionne le curseur à (row, col) — 1-indexé."""
        return self._seq("cup", row - 1, col - 1,
                         fallback=f"\x1b[{row};{col}H".encode())

    def seq_el(self):
        """Efface de la position courante jusqu'à la fin de la ligne."""
        return self._seq("el", fallback=b"\x1b[K")

    def seq_dl1(self):
        """Supprime la ligne courante (scroll up d'une ligne)."""
        return self._seq("dl1", fallback=b"\x1b[M")

    def seq_smso(self):
        """Active la vidéo inverse (fond clair, texte sombre)."""
        return self._seq("smso", fallback=b"\x1b[7m")

    def seq_rmso(self):
        """Désactive la vidéo inverse."""
        return self._seq("rmso", fallback=b"\x1b[27m")

    def seq_civis(self):
        """Masque le curseur."""
        return self._seq("civis")

    def seq_cnorm(self):
        """Affiche le curseur."""
        return self._seq("cnorm")

    def seq_nel(self):
        """Nouvelle ligne (Next Line, équivalent CR+LF)."""
        return self._seq("nel", fallback=b"\x1bE")

    def seq_is2(self):
        """Initialisation partielle du terminal (reset soft)."""
        return self._seq("is2")

    # ------------------------------------------------------------------
    # Raccourcis (send + séquence)
    # ------------------------------------------------------------------

    def clear(self):
        """Efface tout l'écran."""
        self.send(self.seq_clear())

    def cup(self, row: int, col: int):
        self.send(self.seq_cup(row, col))

    def el(self):
        self.send(self.seq_el())

    def smso(self):
        self.send(self.seq_smso())

    def rmso(self):
        self.send(self.seq_rmso())

    def civis(self):
        self.send(self.seq_civis())

    def cnorm(self):
        self.send(self.seq_cnorm())

    def at(self, row: int, col: int, text: str, reverse: bool = False):
        """
        Écrit `text` à la position (row, col), efface la fin de ligne d'abord.

        Paramètres
        ----------
        row     : ligne 1-indexée
        col     : colonne 1-indexée
        text    : texte à afficher (tronqué à COLS)
        reverse : si True, affiche en vidéo inverse
        """
        self.send(self.seq_cup(row, col))
        self.send(self.seq_el())
        if reverse:
            self.send(self.seq_smso())
        self.send(text[:COLS])
        if reverse:
            self.send(self.seq_rmso())

    def clear_window(self, top: int, bottom: int):
        """
        Efface une zone de texte : lignes top à bottom incluses.
        NOTE : les effacements sont toujours délégués à cette méthode,
        jamais inline dans les modules d'action ou de menu.
        """
        for r in range(top, bottom + 1):
            self.send(self.seq_cup(r, 1))
            self.send(self.seq_el())

    # ------------------------------------------------------------------
    # Lecture clavier
    # ------------------------------------------------------------------

    def read_line(self, echo: bool = True, maxlen: int = 80) -> str:
        """
        Lit une ligne clavier caractère par caractère.

        Paramètres
        ----------
        echo   : si True, renvoie chaque caractère à l'écran en temps réel
        maxlen : longueur maximale de saisie

        Gère backspace (codes 8 et 127) et s'arrête sur \\r / \\n.
        Retourne la chaîne saisie (sans retour chariot).
        """
        buf = []
        while True:
            b = self.read(1)
            if not b:
                continue
            ch = b.decode("latin-1", errors="ignore")
            if ch in ("\r", "\n"):
                return "".join(buf)
            if ord(ch) in (8, 127):
                if buf:
                    buf.pop()
                    if echo:
                        self.send("\b \b")
                continue
            if 32 <= ord(ch) <= 126 and len(buf) < maxlen:
                buf.append(ch)
                if echo:
                    self.send(ch)

    def wait_key(self, keys: str = None) -> str:
        """
        Attend qu'une touche soit pressée.

        Paramètres
        ----------
        keys : caractères acceptés (insensible à la casse).
               Si None, n'importe quelle touche imprimable est acceptée.

        Retourne le caractère pressé (en majuscule si keys est précisé).

        Exemple
        -------
            ans = term.wait_key("YN")   # accepte Y ou N
            ans = term.wait_key()       # n'importe quelle touche
        """
        while True:
            b = self.read(1)
            if not b:
                continue
            ch = b.decode("latin-1", errors="ignore")
            if keys is None:
                if 32 <= ord(ch) <= 126:
                    return ch
            else:
                if ch.upper() in keys.upper():
                    return ch.upper()

    def wait_enter(self):
        """
        Attend un appui sur Entrée (\\r ou \\n).
        Utilisé typiquement pour la pagination et les confirmations.
        """
        while True:
            b = self.read(1)
            if b and b.decode("latin-1", errors="ignore") in ("\r", "\n"):
                return

    def beep(self):
        """
        Déclenche le bip interne du Minitel (caractère BEL 0x07).
        Peut être utilisé pour signaler une erreur, un choix invalide,
        ou n'importe quel événement sonore ne nécessitant pas de fichier audio.
        """
        self.send(b"\x07")

    # ------------------------------------------------------------------
    # Utilitaire texte
    # ------------------------------------------------------------------

    # Caractères Unicode fréquents non supportés en latin-1 → substituts ASCII
    TRANS = str.maketrans({
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-",
        "\u2026": "...", "\u00a0": " ",
    })

    @staticmethod
    def safe_line(s: str) -> str:
        """
        Prépare une chaîne pour l'affichage Minitel :
        1. Traduit les caractères Unicode courants vers ASCII/latin-1
        2. Encode en latin-1 pour éliminer tout caractère incompatible

        À utiliser sur toutes les lignes lues depuis des fichiers texte.
        """
        s = s.translate(MinitelTerminal.TRANS)
        return s.encode("latin-1", "ignore").decode("latin-1", "ignore")


# ---------------------------------------------------------------------------
# DebugTerminal : driver stub pour tests sans Minitel physique
# ---------------------------------------------------------------------------

class DebugTerminal(MinitelTerminal):
    """
    Driver de debug : remplace le port série par stdin/stdout.

    Permet de tester la logique de campagne sur un terminal Linux standard
    (xterm, alacritty, etc.) sans Minitel physique.

    Usage : passer --debug en argument de ligne de commande,
            ou instancier Campaign(debug=True).

    Les séquences ANSI sont envoyées directement au terminal Linux.
    Le pacing série est désactivé (page_gap = 0), affichage immédiat.
    """

    def __init__(
        self,
        termname:   str   = None,
        page_chunk: int   = None,
        page_gap:   float = None,
    ):
        self.device     = "debug"
        self.baud       = 0
        self.termname   = termname or os.environ.get("TERM", "xterm-256color")
        self.page_chunk = page_chunk if page_chunk is not None else PAGE_CHUNK
        self.page_gap   = 0.0       # pas de pacing en debug
        self._ser       = None
        self._stdin_fd  = None
        self._old_settings = None

    def open(self):
        """Met stdin en mode raw pour la capture caractère par caractère."""
        import sys, tty, termios
        self._stdin_fd     = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._stdin_fd)
        tty.setraw(self._stdin_fd)

    def close(self):
        """Restaure stdin et nettoie le terminal."""
        import sys, termios
        if self._old_settings and self._stdin_fd is not None:
            termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._old_settings)
        sys.stdout.write("\x1b[?25h\x1b[0m\n")
        sys.stdout.flush()

    def release(self):
        pass

    def reclaim(self):
        pass

    def send(self, data):
        """
        Écrit les données sur stdout.
        latin-1 → UTF-8 pour affichage correct dans un terminal Linux moderne.
        """
        import sys
        if isinstance(data, str):
            data = data.encode("utf-8", errors="ignore")
        else:
            try:
                data = data.decode("latin-1").encode("utf-8")
            except Exception:
                pass
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    def read(self, n=1) -> bytes:
        import sys
        return sys.stdin.buffer.read(n)

    def _seq(self, cap, *args, fallback=b""):
        """Retourne les séquences ANSI standard (pas de tput en mode debug)."""
        fallbacks = {
            "clear":  b"\x1b[2J\x1b[H",
            "el":     b"\x1b[K",
            "dl1":    b"\x1b[M",
            "smso":   b"\x1b[7m",
            "rmso":   b"\x1b[27m",
            "civis":  b"\x1b[?25l",
            "cnorm":  b"\x1b[?25h",
            "nel":    b"\r\n",
            "is2":    b"",
        }
        if cap == "cup" and len(args) >= 2:
            r, c = int(args[0]) + 1, int(args[1]) + 1
            return f"\x1b[{r};{c}H".encode()
        return fallbacks.get(cap, fallback)
