# MinitelRPG Framework

Framework Python pour créer des terminaux RPG sur Minitel.  
Conçu pour *Alien RPG* mais utilisable pour n'importe quel TTRPG.

---

## Structure

```
minitel_rpg/
├── engine/
│   ├── terminal.py    # Primitives Minitel (série, séquences, clavier)
│   ├── audio.py       # LoopPlayer, play_once
│   ├── state.py       # État de session + persistance JSON
│   ├── llm.py         # Abstraction OpenAI / Anthropic / Ollama
│   ├── actions.py     # Boot, TextPage, LLMTerminal, CallbackAction
│   ├── menu.py        # Moteur de menus + événements d'état
│   └── campaign.py    # Orchestrateur principal
│
├── campaigns/
│   ├── destroyer_of_worlds.py   # Campagne complète (exemple)
│   └── nostromo.py              # Campagne alternative (exemple)
│
└── assets/
    ├── destroyer/   # Sons, textes, logos pour Destroyer of Worlds
    └── nostromo/    # Assets pour la campagne Nostromo
```

---

## Créer une campagne

Un fichier Python suffit. Voici la structure minimale :

```python
from minitel_rpg import Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction

# 1. Interface LLM
apollo = LLMTerminal(
    name        = "A.P.O.L.L.O",
    header      = "SEEGSON BIOS 5.3.09.63",
    prompt_file = "assets/prompt.txt",   # ou prompt="Texte direct"
    provider    = "openai",              # "openai" | "anthropic" | "ollama"
    model       = "gpt-4o-mini",
    sounds      = {"typing": "assets/typing.wav"},
)

# 2. Menu
menu = Menu(header="MON TERMINAL", footer="[ENTRER COMMANDE]")
menu.add_choice("1", "INTERFACE IA",    action=apollo)
menu.add_choice("2", "RAPPORT STATUS",  action=TextPage("assets/status.txt"))

# 3. Boot
boot = Boot(
    art              = "assets/art.txt",
    logo             = "assets/logo.txt",
    boot_sound       = "assets/boot.wav",
    loading_duration = 10,
)

# 4. Campagne
campaign = Campaign(device="/dev/ttyUSB0", save_file="ma_campagne.json")
campaign.boot = boot
campaign.menu = menu
campaign.run()
```

---

## Menus conditionnels

Les choix peuvent apparaître ou disparaître selon l'état de session :

```python
# Visible seulement si contamination est True
menu.add_choice(
    "5", "PROTOCOLE DE CONFINEMENT",
    action    = TextPage("confinement.txt"),
    condition = lambda state: state.get("contamination", False),
)

# Toujours visible
menu.add_choice("1", "INTERFACE IA", action=apollo)
```

---

## Sous-menus

Un `action` peut être un autre `Menu` :

```python
sous_menu = Menu(header="PROTOCOLE D'URGENCE")
sous_menu.add_choice("1", "ISOLER SECTION", action=CallbackAction(...))
sous_menu.add_choice("2", "RETOUR",         action=CallbackAction(lambda t, s: None))

menu.add_choice("5", "URGENCE", action=sous_menu)
```

---

## Le LLM modifie l'état

### Via tool use (OpenAI / Anthropic)
Le LLM peut appeler automatiquement `set_state(key, value)`.  
Aucune configuration supplémentaire requise.

### Via commandes texte (tous les providers, dont Ollama)
Le LLM inclut `[SET key=value]` dans sa réponse.  
Ces commandes sont extraites et appliquées, puis retirées du texte affiché.

```
[SET contamination=true]
[SET alert_level=3]
[SET ship_name=Nostromo]
```

---

## Événements d'état

Déclenchez des sons ou messages quand une valeur change :

```python
menu.on_state(
    "contamination",
    value   = True,
    sound   = "assets/alarm.wav",
    message = "!!! CONTAMINATION DÉTECTÉE !!!",
)
```

Le menu se met automatiquement à jour au retour (choix conditionnels réévalués).

---

## Sauvegarde

L'état est persisté en JSON entre les sessions :

```python
campaign = Campaign(save_file="ma_campagne.json")
```

Pour repartir de zéro :
```bash
python campaigns/ma_campagne.py --reset
```

---

## Providers LLM

| Provider   | `provider=`   | Clé API            | Notes                        |
|------------|---------------|--------------------|------------------------------|
| OpenAI     | `"openai"`    | `OPENAI_API_KEY`   | Tool use natif               |
| Anthropic  | `"anthropic"` | `ANTHROPIC_API_KEY`| Tool use natif               |
| Ollama     | `"ollama"`    | —                  | Local, commandes `[SET]` seulement |

La clé API peut aussi être passée directement :
```python
LLMTerminal(..., api_key="sk-...")
```

---

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install pyserial openai anthropic python-dotenv requests
```

Variables d'environnement (fichier `.env`) :
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MINITEL_TERM=minitel1b-80
```

---

## Lancer une campagne

```bash
python campaigns/destroyer_of_worlds.py --device /dev/ttyUSB0 --baud 4800
python campaigns/nostromo.py --device /dev/ttyUSB0 --reset
```
