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

def _has_tool(name: str) -> bool:
    try:
        subprocess.check_output(["which", name], stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

_SOX_AVAILABLE   = _has_tool("play")
_FFPLAY_AVAILABLE = _has_tool("ffplay")


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

LOOP_FADE = 0.1  # durée du fondu entrant/sortant en secondes

def _build_cmd(path: str, volume: float, fade: bool = False) -> list:
    """Construit la commande de lecture selon les outils disponibles.

    Priorité : sox (play) > ffplay > aplay
    - sox et ffplay supportent tous les formats (wav, flac, mp3, ogg...)
    - aplay supporte uniquement le wav
    """
    if _SOX_AVAILABLE:
        cmd = ["play", "-q", path, "vol", str(round(volume, 3))]
        if fade:
            cmd += ["fade", "t", str(LOOP_FADE), "0", str(LOOP_FADE)]
        return cmd
    if _FFPLAY_AVAILABLE:
        vol_filter = str(round(volume, 3))
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                "-af", f"volume={vol_filter}", path]
    # Fallback aplay (wav uniquement)
    return ["aplay", "-q", path]

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
    """Joue un fichier WAV en boucle dans un thread daemon, avec fondu en sortie."""

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

    @staticmethod
    def _audio_duration(path: str) -> float:
        """Retourne la durée en secondes via ffprobe (tous formats) ou wave en fallback."""
        # ffprobe (ffmpeg) — supporte wav, flac, mp3, ogg...
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                stderr=subprocess.DEVNULL
            )
            return float(out.strip())
        except Exception:
            pass
        # Fallback wave pour wav uniquement
        try:
            import wave
            with wave.open(path, 'r') as f:
                return f.getnframes() / f.getframerate()
        except Exception:
            return 0.0

    def _run(self):
        if not self.wav:
            return
        cmd      = _build_cmd(self.wav, self.volume, fade=_SOX_AVAILABLE)
        duration = self._audio_duration(self.wav)
        preload  = 0.05  # lancer le suivant 50ms avant la fin

        try:
            p         = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
            started_at = time.monotonic()
            while not self._stop.is_set():
                time.sleep(0.02)
                if duration > 0:
                    elapsed = time.monotonic() - started_at
                    if elapsed >= duration - preload:
                        if self._stop.is_set():
                            break
                        next_p     = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
                        started_at = time.monotonic()
                        p.wait()
                        p = next_p
            p.terminate()
        except FileNotFoundError:
            pass

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
