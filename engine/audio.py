# -*- coding: utf-8 -*-
"""
engine/audio.py
Gestion audio via aplay (Linux).
"""

import subprocess
import threading
import time


class LoopPlayer:
    """Joue un fichier WAV en boucle dans un thread daemon."""

    def __init__(self, wav_path: str):
        self.wav    = wav_path
        self._stop  = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                p = subprocess.Popen(
                    ["aplay", "-q", self.wav],
                    stderr=subprocess.DEVNULL,
                )
                while p.poll() is None and not self._stop.is_set():
                    time.sleep(0.05)
                if p.poll() is None:
                    p.terminate()
            except FileNotFoundError:
                break  # aplay absent

    def start(self):
        self._thread.start()
        return self  # fluent

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1.0)

    # Context manager
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


def play_once(wav_path: str):
    """Joue un fichier WAV une seule fois (bloquant)."""
    if not wav_path:
        return
    try:
        subprocess.call(["aplay", "-q", wav_path], stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def play_async(wav_path: str):
    """Joue un fichier WAV une seule fois (non bloquant)."""
    if not wav_path:
        return
    try:
        subprocess.Popen(
            ["aplay", "-q", wav_path],
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass
