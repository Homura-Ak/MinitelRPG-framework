# -*- coding: utf-8 -*-
"""
engine/llm.py
Abstraction LLM : OpenAI, Anthropic, Ollama.
Gère :
  - l'historique de conversation
  - les tool calls (function calling) pour modifier l'état
  - le parsing des commandes [SET key=value] dans la réponse texte
"""

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import SessionState


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class LLMProvider:
    """Interface commune à tous les providers."""

    def __init__(self, model: str, system_prompt: str):
        self.model         = model
        self.system_prompt = system_prompt
        self.history: list[dict] = []

    def ask(self, user_message: str, state: "SessionState") -> str:
        """Envoie un message, retourne la réponse nettoyée, met à jour state."""
        raise NotImplementedError

    def reset_history(self):
        self.history = []

    # Injection du contexte d'état dans le system prompt
    def _build_system(self, state: "SessionState") -> str:
        state_summary = "\n".join(
            f"  {k} = {v}" for k, v in state.as_dict().items()
        )
        state_block = (
            f"\n\n[CURRENT SESSION STATE]\n{state_summary}"
            if state_summary else ""
        )
        return self.system_prompt + state_block


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):

    SET_TOOL = {
        "type": "function",
        "function": {
            "name": "set_state",
            "description": (
                "Persist a campaign state variable. "
                "Call this to record events like contamination, alerts, discoveries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key":   {"type": "string",  "description": "Variable name"},
                    "value": {"description": "Value (bool, int, or string)"},
                },
                "required": ["key", "value"],
            },
        },
    }

    def __init__(self, model: str, system_prompt: str, api_key: str = None):
        super().__init__(model, system_prompt)
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

    def ask(self, user_message: str, state: "SessionState") -> str:
        from openai import OpenAI  # already imported above but kept for clarity
        self.history.append({"role": "user", "content": user_message})

        response = self._client.chat.completions.create(
            model    = self.model,
            messages = [{"role": "system", "content": self._build_system(state)}]
                       + self.history,
            tools    = [self.SET_TOOL],
            tool_choice = "auto",
        )

        msg = response.choices[0].message

        # --- Traiter les tool calls ---
        state_changes = {}
        if msg.tool_calls:
            import json
            for tc in msg.tool_calls:
                if tc.function.name == "set_state":
                    args = json.loads(tc.function.arguments)
                    state_changes[args["key"]] = args["value"]

        # --- Texte de réponse ---
        text = msg.content or ""

        # Fallback : commandes [SET] dans le texte
        text = state.apply_llm_commands(text)

        # Appliquer les tool calls
        if state_changes:
            state.update(state_changes)

        self.history.append({"role": "assistant", "content": text})
        return text


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):

    # Cache TTL : "1h" pour les sessions JDR (joueurs lents entre les messages)
    # "5m" si vous voulez revenir au défaut moins coûteux en écriture
    CACHE_TTL = "1h"

    SET_TOOL = {
        "name": "set_state",
        "description": (
            "Persist a campaign state variable. "
            "Call this to record events like contamination, alerts, discoveries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key":   {"type": "string"},
                "value": {"type": ["boolean", "integer", "string"]},
            },
            "required": ["key", "value"],
        },
        # Le tool schema est identique à chaque appel → on le cache aussi
        "cache_control": {"type": "ephemeral", "ttl": CACHE_TTL},
    }

    def __init__(self, model: str, system_prompt: str, api_key: str = None):
        super().__init__(model, system_prompt)
        try:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    def _build_system_blocks(self, state: "SessionState") -> list[dict]:
        """
        Construit le system prompt en deux blocs :
          - Bloc 1 (caché 1h) : le prompt de base, stable toute la session
          - Bloc 2 (non caché) : l'état de session courant, change à chaque tour
        Séparer les deux évite d'invalider le cache quand l'état change.
        """
        blocks = [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral", "ttl": self.CACHE_TTL},
            }
        ]
        state_dict = state.as_dict()
        if state_dict:
            state_summary = "\n".join(f"  {k} = {v}" for k, v in state_dict.items())
            blocks.append({
                "type": "text",
                "text": f"[CURRENT SESSION STATE]\n{state_summary}",
                # Pas de cache ici : change à chaque fois que le LLM modifie l'état
            })
        return blocks

    def ask(self, user_message: str, state: "SessionState") -> str:
        self.history.append({"role": "user", "content": user_message})

        response = self._client.messages.create(
            model      = self.model,
            max_tokens = 1024,
            system     = self._build_system_blocks(state),
            tools      = [self.SET_TOOL],
            messages   = self.history,
        )

        text          = ""
        state_changes = {}

        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use" and block.name == "set_state":
                state_changes[block.input["key"]] = block.input["value"]

        # Fallback [SET] dans le texte
        text = state.apply_llm_commands(text)

        if state_changes:
            state.update(state_changes)

        self.history.append({"role": "assistant", "content": text})

        # Log du cache pour debugging (optionnel)
        usage = response.usage
        if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
            print(f"[cache] hit: {usage.cache_read_input_tokens} tokens lus depuis le cache")
        elif hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens:
            print(f"[cache] write: {usage.cache_creation_input_tokens} tokens écrits en cache")

        return text


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """
    Provider Ollama (ex: llama3, mistral...).
    Pas de tool use natif → on utilise les commandes [SET key=value].
    Le system prompt doit expliquer cette convention au modèle.
    """

    TOOL_INSTRUCTIONS = (
        "\n\nTo modify the campaign state, include commands in your response "
        "using this syntax: [SET key=value]\n"
        "Examples: [SET contamination=true]  [SET alert_level=3]\n"
        "These commands will be processed automatically and removed from the displayed text."
    )

    def __init__(self, model: str, system_prompt: str, base_url: str = "http://localhost:11434"):
        super().__init__(model, system_prompt + self.TOOL_INSTRUCTIONS)
        self.base_url = base_url

    def ask(self, user_message: str, state: "SessionState") -> str:
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests package not installed. Run: pip install requests")

        self.history.append({"role": "user", "content": user_message})

        payload = {
            "model":    self.model,
            "messages": [{"role": "system", "content": self._build_system(state)}]
                        + self.history,
            "stream":   False,
        }

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["message"]["content"]

        # Parse [SET] commands
        text = state.apply_llm_commands(text)

        self.history.append({"role": "assistant", "content": text})
        return text


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_provider(
    provider:      str,
    model:         str,
    system_prompt: str,
    api_key:       str  = None,
    base_url:      str  = None,
) -> LLMProvider:
    """
    Crée le bon provider selon la string 'provider'.
    provider : "openai" | "anthropic" | "ollama"
    """
    p = provider.lower()
    if p == "openai":
        return OpenAIProvider(model, system_prompt, api_key)
    if p == "anthropic":
        return AnthropicProvider(model, system_prompt, api_key)
    if p == "ollama":
        return OllamaProvider(model, system_prompt, base_url or "http://localhost:11434")
    raise ValueError(f"Unknown LLM provider: '{provider}'. Choose openai, anthropic, or ollama.")
