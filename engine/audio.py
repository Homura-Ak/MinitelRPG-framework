# -*- coding: utf-8 -*-
"""
engine/audio.py
Gestion audio via aplay (sans volume) ou sox/play (avec volume).

Volume : float de 0.0 (silence) à 1.0 (normal) et au-delà pour amplifier.
Si sox n'est pas installé, le volume est ignoré et aplay est utilisé.

Installation sox :
    sudo apt install sox
"""

import subprocess
import threading
import time


# ---------------------------------------------------------------------------
# Détection sox au démarrage
# ---------------------------------------------------------------------------

def _has_sox() -> bool:
    try:
        subprocess.check_output(["which", "play"], stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

_SOX_AVAILABLE = _has_sox()


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _build_cmd(wav_path: str, volume: float) -> list:
    """Construit la commande de lecture selon la disponibilité de sox."""
    if _SOX_AVAILABLE and volume != 1.0:
        return ["play", "-q", wav_path, "vol", str(round(volume, 3))]
    return ["aplay", "-q", wav_path]


# ---------------------------------------------------------------------------
# Sound : conteneur chemin + volume
# ---------------------------------------------------------------------------

class Sound:
    """
    Associe un fichier WAV à un volume.

    Usage :
        Sound("assets/horn.wav", volume=0.5)

    Dans une campagne :
        sounds = {
            "thinking": Sound(sound("rattle.wav"), volume=0.4),
            "typing":   Sound(sound("typing.wav"), volume=0.8),
        }

    Compatibilité : on peut toujours passer une simple string,
    les fonctions play_once/play_async/LoopPlayer acceptent les deux.
    """

    def __init__(self, path: str, volume: float = 1.0):
        self.path   = path
        self.volume = volume

    def __str__(self):
        return self.path

    @staticmethod
    def resolve(src) -> tuple:
        """Retourne (path, volume) depuis une string ou un Sound."""
        if src is None:
            return None, 1.0
        if isinstance(src, Sound):
            return src.path, src.volume
        return str(src), 1.0


# ---------------------------------------------------------------------------
# LoopPlayer
# ---------------------------------------------------------------------------

class LoopPlayer:
    """Joue un fichier WAV en boucle dans un thread daemon."""

    def __init__(self, src, volume: float = None):
        """
        src    : str ou Sound
        volume : surcharge le volume du Sound si précisé
        """
        path, vol = Sound.resolve(src)
        self.wav    = path
        self.volume = volume if volume is not None else vol
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        if not self.wav:
            return
        cmd = _build_cmd(self.wav, self.volume)
        while not self._stop.is_set():
            try:
                p = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
                while p.poll() is None and not self._stop.is_set():
                    time.sleep(0.05)
                if p.poll() is None:
                    p.terminate()
            except FileNotFoundError:
                break

    def start(self):
        if self.wav:
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1.0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


# ---------------------------------------------------------------------------
# play_once / play_async
# ---------------------------------------------------------------------------

def play_once(src, volume: float = None):
    """Joue un fichier WAV une seule fois (bloquant)."""
    path, vol = Sound.resolve(src)
    if not path:
        return
    v = volume if volume is not None else vol
    try:
        subprocess.call(_build_cmd(path, v), stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def play_async(src, volume: float = None):
    """Joue un fichier WAV une seule fois (non bloquant)."""
    path, vol = Sound.resolve(src)
    if not path:
        return
    v = volume if volume is not None else vol
    try:
        subprocess.Popen(_build_cmd(path, v), stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass
