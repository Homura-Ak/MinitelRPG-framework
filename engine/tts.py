# -*- coding: utf-8 -*-
"""
engine/tts.py
=============
Module Text-To-Speech via OpenAI TTS API.

Lecture asynchrone avec arrêt immédiat sur demande.
Priorité de lecture : sox (play) > ffplay > aplay
- sox    : supporte les effets audio (pitch, echo, overdrive...)
- ffplay : lecture simple tous formats
- aplay  : fallback wav uniquement

Usage dans une campagne
-----------------------
    from engine.tts import TTSConfig, speak_async

    tts = TTSConfig(
        voice        = "onyx",
        model        = "gpt-4o-mini-tts",
        instructions = "Speak in a cold, robotic, synthetic computer voice.",
        alsa_device  = "plughw:1,0",
    )

    handle = speak_async("SEVASTOLINK EN LIGNE", tts)
    handle.stop()  # interrompt la lecture
"""

import os
import tempfile
import threading
import subprocess
from typing import Optional


# ---------------------------------------------------------------------------
# Détection des outils audio (même logique que audio.py)
# ---------------------------------------------------------------------------

def _has_tool(name: str) -> bool:
    try:
        subprocess.check_output(["which", name], stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

_SOX_AVAILABLE    = _has_tool("play")
_FFPLAY_AVAILABLE = _has_tool("ffplay")


# ---------------------------------------------------------------------------
# Construction de la commande de lecture
# ---------------------------------------------------------------------------

def _build_play_cmd(path: str, alsa_device: str, robotic: bool) -> list:
    """
    Construit la commande de lecture selon les outils disponibles.

    sox    : lecture + effets robotiques si robotic=True
    ffplay : lecture simple
    aplay  : fallback wav
    """
    if _SOX_AVAILABLE:
        cmd = ["play", "-q", path]
        if robotic:
            cmd += [
                "pitch", "-80",
                "echo", "0.8", "0.9", "30", "0.3",
                "overdrive", "20",
            ]
        return cmd

    if _FFPLAY_AVAILABLE:
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]

    # Fallback aplay
    cmd = ["aplay", "-q"]
    if alsa_device:
        cmd += ["-D", alsa_device]
    cmd += [path]
    return cmd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TTSConfig:
    """
    Paramètres TTS centralisés, à instancier une fois dans la campagne.

    Paramètres
    ----------
    api_key      : clé OpenAI (lu depuis OPENAI_API_KEY si absent)
    voice        : voix OpenAI — alloy, echo, fable, onyx, nova, shimmer
                   (défaut: onyx — grave, sobre, idéal pour APOLLO)
    model        : modèle TTS (défaut: gpt-4o-mini-tts — supporte instructions)
    speed        : vitesse 0.25-4.0 (défaut: 0.9)
    alsa_device  : device ALSA (défaut: plughw:1,0)
    robotic      : applique effets sox pitch/echo/overdrive (défaut: True)
                   ignoré si sox n'est pas installé
    enabled      : False pour désactiver sans changer le code
    instructions : instructions de style vocal pour gpt-4o-mini-tts
                   ignoré par tts-1
    """

    def __init__(
        self,
        api_key:      str   = None,
        voice:        str   = "alloy",
        model:        str   = "gpt-4o-mini-tts",
        speed:        float = 1,
        alsa_device:  str   = "plughw:1,0",
        robotic:      bool  = True,
        enabled:      bool  = True,
        instructions: str   = (
            "Parle en une froide, robotique, synthetique voix d'ordinateur. "
            "Monotone, pas d'émotions, comme l'ordinateur de bord IA MUTHUR d'alien."
            "Prononce les mots Francais correctement. Paie attention aux accents comme 'ç' dans 'reçu'."
        ),
    ):
        self.api_key      = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.voice        = voice
        self.model        = model
        self.speed        = speed
        self.alsa_device  = alsa_device
        self.robotic      = robotic
        self.enabled      = enabled
        self.instructions = instructions


# ---------------------------------------------------------------------------
# Handle de lecture
# ---------------------------------------------------------------------------

class TTSHandle:
    """
    Représente une lecture TTS en cours.
    Appeler stop() pour interrompre immédiatement.
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._player: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def _set_player(self, proc: subprocess.Popen):
        with self._lock:
            self._player = proc

    def stop(self):
        """Arrête la lecture immédiatement."""
        self._stop_event.set()
        with self._lock:
            if self._player and self._player.poll() is None:
                try:
                    self._player.terminate()
                except Exception:
                    pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def wait(self):
        """Attend la fin naturelle de la lecture."""
        if self._thread:
            self._thread.join()

    @property
    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


# ---------------------------------------------------------------------------
# Handle no-op (TTS désactivé)
# ---------------------------------------------------------------------------

class _NullHandle:
    """Handle retourné quand le TTS est désactivé."""
    def stop(self): pass
    def wait(self): pass
    @property
    def is_playing(self): return False


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------

def speak_async(text: str, config: TTSConfig) -> TTSHandle:
    """
    Lance la synthèse vocale en arrière-plan.

    Retourne immédiatement un TTSHandle.
    Appeler handle.stop() pour interrompre.
    Si config.enabled est False, retourne un handle no-op.

    Le fichier audio temporaire est supprimé après lecture.
    """
    if not config or not config.enabled or not text or not text.strip():
        return _NullHandle()

    handle = TTSHandle()

    def _run():
        tmp_path = None
        try:
            if handle._stop_event.is_set():
                return

            import urllib.request
            import urllib.error
            import json

            payload = json.dumps({
                "model":           config.model,
                "input":           text[:4096],
                "voice":           config.voice,
                "speed":           config.speed,
                "response_format": "wav",
                "instructions":    config.instructions,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/speech",
                data    = payload,
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type":  "application/json",
                },
                method = "POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    audio_data = resp.read()
            except urllib.error.HTTPError as e:
                print(f"[tts] HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
                return
            except Exception as e:
                print(f"[tts] Erreur requête: {e}")
                return

            if handle._stop_event.is_set():
                return

            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            with os.fdopen(fd, "wb") as f:
                f.write(audio_data)

            if handle._stop_event.is_set():
                return

            # Lecture avec fallback sox > ffplay > aplay
            if _SOX_AVAILABLE and config.alsa_device:
                os.environ.setdefault("AUDIODRIVER", "alsa")
                os.environ.setdefault("AUDIODEV", config.alsa_device)

            cmd = _build_play_cmd(tmp_path, config.alsa_device, config.robotic)
            proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
            handle._set_player(proc)
            proc.wait()

        except Exception as e:
            print(f"[tts] Erreur: {e}")
        finally:
            if tmp_path and os.path.isfile(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    handle._thread = threading.Thread(target=_run, daemon=True)
    handle._thread.start()
    return handle
