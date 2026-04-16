# -*- coding: utf-8 -*-
"""
engine/state.py
État de session avec persistance JSON sur disque.
Supporte les watchers : callbacks déclenchés quand une clé change.
"""

import json
import os
import time
from typing import Any, Callable


class SessionState:
    """
    Dict-like persistent state.

    Usage :
        state = SessionState("campaign_save.json")
        state["contamination"] = True   # sauvegarde auto + déclenche watchers
        val = state.get("contamination", False)
        state.reset()                   # remet à zéro
    """

    def __init__(self, save_path: str = None):
        self._path: str | None = save_path
        self._data: dict       = {}
        self._watchers: dict[str, list[Callable]] = {}

        if save_path and os.path.isfile(save_path):
            self._load()

    # ------------------------------------------------------------------
    # Accès dict-like
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key: str):
        return self._data[key]

    def __setitem__(self, key: str, value: Any):
        old = self._data.get(key)
        self._data[key] = value
        self._save()
        if old != value:
            self._fire(key, value)

    def __contains__(self, key: str):
        return key in self._data

    def update(self, mapping: dict):
        changed = {}
        for k, v in mapping.items():
            old = self._data.get(k)
            self._data[k] = v
            if old != v:
                changed[k] = v
        self._save()
        for k, v in changed.items():
            self._fire(k, v)

    def reset(self):
        self._data = {}
        self._save()

    def as_dict(self) -> dict:
        return dict(self._data)

    # ------------------------------------------------------------------
    # Watchers
    # ------------------------------------------------------------------

    def watch(self, key: str, callback: Callable[[Any], None]):
        """
        Enregistre un callback déclenché quand `key` change.
        callback(new_value)
        """
        self._watchers.setdefault(key, []).append(callback)

    def _fire(self, key: str, value: Any):
        for cb in self._watchers.get(key, []):
            try:
                cb(value)
            except Exception as e:
                print(f"[state] watcher error on '{key}': {e}")

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------

    def _save(self):
        if not self._path:
            return
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._data = {}

    # ------------------------------------------------------------------
    # Injection LLM : parse les commandes [SET key=value] dans un texte
    # ------------------------------------------------------------------

    def apply_llm_commands(self, text: str) -> str:
        """
        Extrait et applique les commandes [SET key=value] du texte LLM.
        Retourne le texte nettoyé (sans les balises).

        Exemples supportés :
            [SET contamination=true]
            [SET alert_level=3]
            [SET ship_name=Nostromo]
        """
        import re
        pattern = re.compile(r"\[SET\s+(\w+)\s*=\s*([^\]]+)\]", re.IGNORECASE)
        changes = {}
        for match in pattern.finditer(text):
            key   = match.group(1).strip()
            raw   = match.group(2).strip()
            value = self._coerce(raw)
            changes[key] = value

        cleaned = pattern.sub("", text).strip()
        if changes:
            self.update(changes)
        return cleaned

    @staticmethod
    def _coerce(raw: str):
        """Convertit une string en bool / int / float / str."""
        if raw.lower() in ("true", "yes", "oui"):
            return True
        if raw.lower() in ("false", "no", "non"):
            return False
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw
