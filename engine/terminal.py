# -*- coding: utf-8 -*-
"""
engine/terminal.py
Primitives bas niveau pour le Minitel : envoi série, séquences ANSI/terminfo,
lecture clavier, rendu de texte.
"""

import os
import subprocess
import time
import serial

# ---------------------------------------------------------------------------
# Config par défaut (surchargeable via MinitelTerminal)
# ---------------------------------------------------------------------------
PAGE_CHUNK  = 32
PAGE_GAP    = 0.01
COLS        = 80
LINES       = 24

TERMNAME = os.environ.get("MINITEL_TERM", "minitel1b-80")

# ---------------------------------------------------------------------------
# Helpers terminfo
# ---------------------------------------------------------------------------

def tput(name, *args, termname=None):
    t = termname or TERMNAME
    cmd = ["tput", "-T", t, name]
    if args:
        cmd += [str(a) for a in args]
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return b""


# ---------------------------------------------------------------------------
# Classe principale : encapsule le port série + toutes les primitives
# ---------------------------------------------------------------------------

class MinitelTerminal:
    """
    Wrapper autour d'un objet serial.Serial.
    Expose send(), cup(), clear(), el(), etc.
    Peut être ouvert/fermé/rouvert sans recréer l'objet.
    """

    def __init__(self, device: str, baud: int, termname: str = None):
        self.device   = device
        self.baud     = baud
        self.termname = termname or TERMNAME
        self._ser: serial.Serial | None = None

    # ------------------------------------------------------------------
    # Cycle de vie du port
    # ------------------------------------------------------------------

    def open(self):
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(
            self.device,
            baudrate  = self.baud,
            bytesize  = serial.SEVENBITS,
            parity    = serial.PARITY_EVEN,
            stopbits  = serial.STOPBITS_ONE,
            xonxoff   = True,
            rtscts    = False,
            dsrdtr    = False,
            timeout   = 0.1,
        )

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def release(self):
        """Ferme le port pour le céder temporairement à un sous-process."""
        self.close()

    def reclaim(self):
        """Réouvre le port après retour d'un sous-process."""
        self.open()

    @property
    def port(self):
        return self.device

    @property
    def baudrate(self):
        return self.baud

    # ------------------------------------------------------------------
    # Envoi série (pacing pour Minitel)
    # ------------------------------------------------------------------

    def send(self, data):
        if isinstance(data, str):
            data = data.encode("latin-1", errors="ignore")
        for i in range(0, len(data), PAGE_CHUNK):
            self._ser.write(data[i : i + PAGE_CHUNK])
            self._ser.flush()
            time.sleep(PAGE_GAP)

    def read(self, n=1) -> bytes:
        return self._ser.read(n)

    # ------------------------------------------------------------------
    # Séquences terminfo avec fallback ANSI
    # ------------------------------------------------------------------

    def _seq(self, cap, *args, fallback=b""):
        s = tput(cap, *args, termname=self.termname)
        return s if s else fallback

    def seq_clear(self):
        return self._seq("clear", fallback=b"\x1b[2J\x1b[H")

    def seq_cup(self, row: int, col: int):
        return self._seq("cup", row - 1, col - 1,
                         fallback=f"\x1b[{row};{col}H".encode())

    def seq_el(self):
        return self._seq("el", fallback=b"\x1b[K")

    def seq_dl1(self):
        return self._seq("dl1", fallback=b"\x1b[M")

    def seq_smso(self):
        return self._seq("smso", fallback=b"\x1b[7m")

    def seq_rmso(self):
        return self._seq("rmso", fallback=b"\x1b[27m")

    def seq_civis(self):
        return self._seq("civis")

    def seq_cnorm(self):
        return self._seq("cnorm")

    def seq_nel(self):
        return self._seq("nel", fallback=b"\x1bE")

    def seq_is2(self):
        return self._seq("is2")

    # ------------------------------------------------------------------
    # Raccourcis pratiques
    # ------------------------------------------------------------------

    def clear(self):
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

    def at(self, row: int, col: int, text: str, reverse=False):
        """Écrit `text` à la position (row, col), optionnellement en vidéo inverse."""
        self.send(self.seq_cup(row, col))
        self.send(self.seq_el())
        if reverse:
            self.send(self.seq_smso())
        self.send(text[:COLS])
        if reverse:
            self.send(self.seq_rmso())

    def clear_window(self, top: int, bottom: int):
        for r in range(top, bottom + 1):
            self.send(self.seq_cup(r, 1))
            self.send(self.seq_el())

    # ------------------------------------------------------------------
    # Lecture clavier
    # ------------------------------------------------------------------

    def read_line(self, echo=True, maxlen=80) -> str:
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

    def wait_enter(self):
        while True:
            b = self.read(1)
            if b and b.decode("latin-1", errors="ignore") in ("\r", "\n"):
                return

    # ------------------------------------------------------------------
    # Utilitaire texte
    # ------------------------------------------------------------------

    TRANS = str.maketrans({
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-",
        "\u2026": "...", "\u00a0": " ",
    })

    @staticmethod
    def safe_line(s: str) -> str:
        s = s.translate(MinitelTerminal.TRANS)
        return s.encode("latin-1", "ignore").decode("latin-1", "ignore")


# ---------------------------------------------------------------------------
# Mode debug : terminal Linux au lieu du port série
# ---------------------------------------------------------------------------

class DebugTerminal(MinitelTerminal):
    """
    Remplace le port série par stdin/stdout.
    Les séquences ANSI sont envoyées directement au terminal Linux.
    Utilisé avec --debug pour tester sans Minitel.
    """

    def __init__(self, termname: str = None):
        # Pas d'appel à super().__init__() avec serial
        self.device   = "debug"
        self.baud     = 0
        self.termname = termname or os.environ.get("TERM", "xterm-256color")
        self._ser     = None
        self._stdin_fd = None

    def open(self):
        import sys, tty, termios
        self._stdin_fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._stdin_fd)
        tty.setraw(self._stdin_fd)

    def close(self):
        import sys, termios
        if self._old_settings and self._stdin_fd is not None:
            termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, self._old_settings)
        # Remettre le curseur et le terminal propre
        sys.stdout.write("\x1b[?25h\x1b[0m\n")
        sys.stdout.flush()

    def release(self):
        pass

    def reclaim(self):
        pass

    def send(self, data):
        import sys
        if isinstance(data, str):
            data = data.encode("utf-8", errors="ignore")
        else:
            # Convertir latin-1 → utf-8 pour affichage correct dans le terminal
            try:
                data = data.decode("latin-1").encode("utf-8")
            except Exception:
                pass
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    def read(self, n=1) -> bytes:
        import sys
        return sys.stdin.buffer.read(n)

    # Les séquences utilisent le terminal courant (xterm/etc) via fallback ANSI
    def _seq(self, cap, *args, fallback=b""):
        # En mode debug on utilise directement les fallback ANSI
        # car le terminal Linux les supporte nativement
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
