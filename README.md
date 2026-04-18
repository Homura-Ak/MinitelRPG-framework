# MinitelRPG Framework

Framework Python pour créer des terminaux RPG sur Minitel.
Conçu pour *Alien RPG* mais utilisable pour n'importe quel TTRPG.

---

## Table des matières

1. [Installation](#installation)
2. [Lancer une campagne](#lancer-une-campagne)
3. [Structure du projet](#structure-du-projet)
4. [Créer une campagne — guide complet](#créer-une-campagne)
   - [Boot](#boot--séquence-de-démarrage)
   - [Menu classique](#menu--menu-classique)
   - [SplitMenu](#splitmenu--menu-deux-colonnes)
   - [TextPage](#textpage--affichage-de-texte)
   - [LLMTerminal](#llmterminal--interface-ia)
   - [CallbackAction](#callbackaction--action-python-libre)
   - [Sons](#sons--personnaliser-laudio)
   - [État de session](#état-de-session--variables-persistantes)
   - [Menus conditionnels](#menus-conditionnels)
   - [Événements d'état](#événements-détat)
5. [Référence complète des paramètres](#référence-complète-des-paramètres)
6. [Providers LLM](#providers-llm)
7. [Persistance et reset](#persistance-et-reset)
8. [Mode debug](#mode-debug)
9. [Démarrage automatique sur Raspberry Pi](#démarrage-automatique-sur-raspberry-pi)

---

## Installation

### 1. Dépendances système

```bash
# Lecture audio (sox pour le volume, ffmpeg pour les formats non-wav)
sudo apt install sox ffmpeg
```

### 2. Environnement Python

```bash
# Créer le venv (à faire une seule fois)
python3 -m venv venv

# Activer le venv (à faire à chaque session)
source venv/bin/activate

# Installer les dépendances depuis le requirements.txt
pip install -r requirements.txt
```

> **Important :** un venv ne se copie pas d'une machine à l'autre — il faut toujours le recréer sur place avec `pip install -r requirements.txt`.

### 3. Variables d'environnement

Créer un fichier `.env` à la racine du projet :

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MINITEL_TERM=minitel1b-80
```

---

## Lancer une campagne

```bash
# Minitel physique
python campaigns/exemple.py --device /dev/ttyUSB0 --baud 4800

# Mode debug (terminal Linux, sans Minitel)
python campaigns/exemple.py --debug

# Repartir de zéro (efface la sauvegarde)
python campaigns/exemple.py --reset --debug
```

---

## Structure du projet

```
minitelrpg/
├── engine/
│   ├── terminal.py    # Driver Minitel (port série, séquences, clavier)
│   ├── audio.py       # Lecture audio : LoopPlayer, play_once, Sound
│   ├── state.py       # État de session + persistance JSON
│   ├── llm.py         # Abstraction OpenAI / Anthropic / Ollama
│   ├── actions.py     # Boot, TextPage, LLMTerminal, CallbackAction
│   ├── menu.py        # Menu classique + événements d'état
│   └── menusplit.py   # SplitMenu (deux colonnes style Alien Isolation)
│
├── campaigns/
│   ├── exemple.py     # Campagne d'exemple complète (à copier/adapter)
│   └── sevastolink.py # Campagne Alien RPG "Destroyer of Worlds"
│
└── assets/
    ├── exemple/       # Sons, textes, logos pour la campagne exemple
    └── sevastolink/   # Assets pour SEVASTOLINK
```

---

## Créer une campagne

Un fichier Python dans `campaigns/` suffit. Copiez `exemple.py` comme point de départ.

### Imports minimaux

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction, MenuExit, Sound
from engine import SplitMenu, AudioItem  # si vous utilisez le menu deux colonnes
```

---

### Boot — séquence de démarrage

Le `Boot` est la séquence jouée au lancement : art ASCII, confirmation, logo, défilement de texte, barre de chargement.

```python
boot = Boot(
    # Fichiers d'assets
    art         = "assets/art.txt",      # art ASCII affiché sur l'écran de boot
    scroll_text = "assets/boot.txt",     # texte qui défile après confirmation
    logo        = "assets/logo.txt",     # logo affiché en plein écran quelques secondes

    # Durées et vitesses
    logo_display_duration = 5.0,   # secondes d'affichage du logo
    loading_duration      = 8,     # secondes de la barre de chargement
    scroll_delay          = 0.08,  # pause entre chaque ligne du défilement (+ lent = + grand)

    # Sons (str ou Sound(path, volume=0.x))
    boot_sound    = Sound("assets/sounds/boot.wav", volume=0.8),
    beep_sound    = "assets/sounds/beep.wav",     # bip immédiat après confirmation
    typing_sound  = Sound("assets/sounds/typing.wav", volume=0.3),  # pendant le défilement
    loading_sound = "assets/sounds/hum.wav",      # pendant la barre de chargement
    final_sound   = "assets/sounds/horn.wav",     # à la fin du boot

    # Invite et touches
    prompt      = "  INITIALISER SYSTEME ? (Y/N) : ",  # texte du prompt
    confirm_key = "Y",   # touche pour confirmer (insensible casse)
    cancel_key  = "N",   # touche pour annuler
)
```

**Paramètre `scroll_delay` :** `0.05` = très rapide, `0.10` = normal, `0.20` = lent dramatique.

---

### Menu — menu classique

Le `Menu` affiche des choix numérotés ou par lettres. L'utilisateur tape la touche puis Entrée.

```python
menu = Menu(
    # Textes d'affichage
    header        = "SEEGSON BIOS 5.3.09.63",
    subheader     = "APOLLO STATION — HADLEY'S HOPE",
    footer        = "[ENTRER COMMANDE] > ",
    header_prefix = "# - ",   # mettre "" pour aucun préfixe

    # Format des choix
    choice_format  = "{key} - {label}",  # format par défaut
    # Exemples alternatifs :
    # choice_format = "{key}) {label}"
    # choice_format = "  [{key}] {label}"
    choice_indent  = 4,    # colonne de départ des choix (défaut 4)
    menu_row_start = 7,    # première ligne des choix (défaut 7, après le header)

    # Son et messages
    typing_sound = Sound("assets/sounds/typing.wav", volume=0.3),
    unknown_msg  = "[ERREUR] Commande inconnue : {key}",
)

# Ajout de choix
menu.add_choice("1", "A.P.O.L.L.O",    action=apollo_terminal)
menu.add_choice("2", "POWER STATUS",    action=TextPage("assets/power.txt"))
menu.add_choice("Q", "QUITTER",
    action = CallbackAction(lambda t, s: (_ for _ in ()).throw(MenuExit()))
)
```

---

### SplitMenu — menu deux colonnes

Le `SplitMenu` affiche une liste à gauche et un panneau de contenu à droite.
Navigation par flèches directionnelles.

```python
terminal = SplitMenu(
    header       = "SEVASTOLINK TERMINAL v2.1",
    folder_label = "FICHIERS",
    footer       = None,          # None = construit automatiquement

    typing_sound   = Sound("assets/sounds/typing.wav", volume=0.3),
    response_delay = 0.08,        # pause entre les lignes d'un TextPage ouvert

    exit_key = "Q",

    # Touches de navigation (par défaut : flèches ANSI)
    # key_up    = b'\x1b[A'   (flèche haut)
    # key_down  = b'\x1b[B'   (flèche bas)
    # key_open  = b'\x1b[C'   (flèche droite — ouvrir)
    # key_back  = b'\x1b[D'   (flèche gauche — retour)
    # key_enter = b'\r'        (Entrée — confirmer)

    # Textes des labels de navigation dans le footer
    nav_navigate = "[HAUT/BAS] NAVIGUER",
    nav_open     = "[DROITE] OUVRIR",
    nav_back     = "[GAUCHE] RETOUR",
    nav_play     = "[ENTREE] JOUER",
    nav_quit     = "[Q] QUITTER",
)

terminal.add_item("DOSSIER PERSO", action=perso_folder)
terminal.add_item("LOGS AUDIO",    action=audio_folder)
terminal.add_item(
    "INTERFACE A.P.O.L.L.O",
    action    = apollo_terminal,
    condition = lambda s: s.get("apollo_unlocked", True),
)
```

**Sous-dossiers :** un item peut pointer vers un autre `SplitMenu`.

```python
audio_folder = SplitMenu(header="LOGS AUDIO", folder_label="FICHIERS AUDIO")
audio_folder.add_item("LOG 01", action=AudioItem("sounds/log01.wav", "Journal Marlow"))
audio_folder.add_item("LOG 02", action=AudioItem("sounds/log02.wav", "Journal Verlaine"))

terminal.add_item("LOGS AUDIO", action=audio_folder)
```

---

### TextPage — affichage de texte

Affiche un fichier texte paginé (une page à la fois, Entrée pour continuer).

```python
TextPage(
    path         = "assets/rapport.txt",
    typing_sound = Sound("assets/sounds/typing.wav", volume=0.4),
    scroll_delay = 0.10,   # pause entre les lignes (+ élevé = + lent)

    # Textes de pagination
    footer_next = "[PAGE SUIVANTE — APPUYER SUR ENTREE]",
    footer_end  = "[FIN DU DOCUMENT — APPUYER SUR ENTREE]",

    # Header affiché au-dessus du texte (défaut : nom du fichier)
    header = "RAPPORT DE SITUATION",
)
```

---

### LLMTerminal — interface IA

Interface de chat avec un LLM affiché sur le Minitel.

```python
apollo = LLMTerminal(
    # Identité de l'IA
    name         = "A.P.O.L.L.O",
    header       = "# - A.P.O.L.L.O - CENTRAL ARTIFICIAL INTELLIGENCE",
    input_prompt = "ENTER QUERY",

    # Prompt système
    prompt_file  = "assets/prompt_apollo.txt",
    # ou : prompt = "You are APOLLO, an onboard AI...",

    # Provider LLM
    provider = "anthropic",
    model    = "claude-sonnet-4-6",
    api_key  = None,   # None = lue depuis l'environnement

    # Sons
    sounds = {
        "typing":   Sound("assets/sounds/typing.wav", volume=0.4),
        "thinking": Sound("assets/sounds/thinking.wav", volume=0.4),
    },

    # Commande de sortie
    exit_command = "/exit",

    # Vitesse d'affichage des réponses
    response_delay = 0.03,   # pause entre les lignes (défaut 0.02)

    # Séquence de boot optionnelle
    boot_prompt       = "INITIALISER A.P.O.L.L.O ? (Y/N) : ",
    boot_confirm      = "Y",
    boot_logo         = "assets/logo-seegson.txt",
    boot_sound        = "assets/sounds/typing.wav",
    boot_scroll_delay = 0.10,

    # Labels d'interface
    label_you      = "[YOU]",
    label_thinking = "PROCESSING...",
    error_prefix   = "[SYSTEM ERROR]",
)
```

#### Le LLM peut modifier l'état

**Via tool use (OpenAI / Anthropic) :** automatique, aucune config.

**Via commandes texte (tous providers, dont Ollama) :**
```
[SET contamination=true]
[SET alert_level=3]
[SET ship_name=Nostromo]
```
Les commandes sont extraites et appliquées, puis retirées du texte affiché.

---

### CallbackAction — action Python libre

```python
# Exemple simple
CallbackAction(
    fn    = lambda term, state: state.update({"power_on": True}),
    sound = "assets/sounds/click.wav",   # son joué avant fn (optionnel)
)

# Exemple avancé
def activer_urgence(term, state):
    state.update({"urgence": True, "contamination": True})
    term.at(12, 4, ">>> PROTOCOLE D'URGENCE ACTIVE <<<")
    term.wait_enter()

menu.add_choice("U", "URGENCE", action=CallbackAction(fn=activer_urgence))

# Quitter un sous-menu
menu.add_choice("R", "RETOUR",
    action = CallbackAction(lambda t, s: (_ for _ in ()).throw(MenuExit()))
)
```

---

### Sons — personnaliser l'audio

**Deux façons de spécifier un son :**

```python
# 1. Chemin simple (volume 1.0 par défaut)
typing_sound = "assets/sounds/typing.wav"

# 2. Avec volume explicite (nécessite sox ou ffmpeg)
typing_sound = Sound("assets/sounds/typing.wav", volume=0.4)
```

**Bip Minitel natif (sans fichier audio) :**
```python
term.beep()   # déclenche le bip interne du Minitel (caractère BEL)
```

**Tableau récapitulatif des sons disponibles :**

| Module | Paramètre son | Moment |
|--------|--------------|--------|
| `Boot` | `boot_sound` | pendant l'affichage de l'art ASCII |
| `Boot` | `beep_sound` | immédiatement après confirmation |
| `Boot` | `typing_sound` | pendant le défilement du texte |
| `Boot` | `loading_sound` | pendant la barre de chargement |
| `Boot` | `final_sound` | à la fin du boot |
| `Menu` | `typing_sound` | pendant l'affichage des choix |
| `Choice` | `sounds["select"]` | quand ce choix est activé |
| `TextPage` | `typing_sound` | pendant l'écriture de chaque page |
| `LLMTerminal` | `sounds["typing"]` | pendant l'affichage de la réponse |
| `LLMTerminal` | `sounds["thinking"]` | pendant l'attente LLM |
| `LLMTerminal` | `boot_sound` | pendant le défilement du logo de boot |
| `SplitMenu` | `typing_sound` | pendant l'affichage des items |
| `AudioItem` | — | fichier audio joué en lecture |
| `StateEvent` | `sound` | quand l'événement se déclenche |
| `CallbackAction` | `sound` | avant d'exécuter la fonction |

---

### État de session — variables persistantes

L'état est un dictionnaire persisté en JSON entre les sessions.

```python
# Lire une valeur (avec valeur par défaut)
contamination = state.get("contamination", False)

# Écrire une valeur
state["contamination"] = True

# Écrire plusieurs valeurs d'un coup
state.update({"contamination": True, "alert_level": 3})

# Réinitialiser
state.reset()
```

Dans un `CallbackAction` :
```python
CallbackAction(lambda term, state: state.update({"muthur_unlocked": True}))
```

---

### Menus conditionnels

Un choix peut être masqué selon l'état :

```python
# Visible seulement si contamination est True
menu.add_choice(
    "5", "PROTOCOLE DE CONFINEMENT [ACTIF]",
    action    = confinement_menu,
    condition = lambda state: state.get("contamination", False),
    sounds    = {"select": Sound("alarm.wav", volume=0.8)},
)

# Visible seulement si MU/TH/UR n'est pas encore débloquée
menu.add_choice(
    "U", "DEBLOQUER MU/TH/UR [GM]",
    action    = CallbackAction(lambda t, s: s.update({"muthur_unlocked": True})),
    condition = lambda state: not state.get("muthur_unlocked", False),
)
```

Même chose dans un `SplitMenu` :
```python
terminal.add_item(
    "A.P.O.L.L.O [RESTREINT]",
    action    = apollo,
    condition = lambda s: s.get("apollo_unlocked", False),
)
```

---

### Événements d'état

Déclenchés automatiquement quand une valeur d'état change, même si c'est le LLM qui l'a modifiée.

```python
# Alerte plein écran quand la contamination passe à True
menu.on_state(
    "contamination",
    value        = True,
    sound        = Sound("sounds/horn.wav", volume=1.0),
    message_file = "assets/contamination_alert.txt",
)

# Message court quand la contamination est neutralisée
menu.on_state(
    "contamination",
    value   = False,
    sound   = "sounds/beep.wav",
    message = "Contamination neutralisee. Retour a la normale.",
)

# Callback custom
menu.on_state(
    "muthur_unlocked",
    value    = True,
    message  = "Acces MU/TH/UR 6000 deverrouille.",
    callback = lambda term, state: term.beep(),
)
```

Le menu se re-render automatiquement au retour (les choix conditionnels sont réévalués).

---

## Référence complète des paramètres

### Boot

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `art` | str | None | Fichier art ASCII affiché sur l'écran de boot |
| `scroll_text` | str | None | Fichier texte défilant après confirmation |
| `logo` | str | None | Fichier logo affiché en plein écran |
| `logo_display_duration` | float | 3.0 | Durée du logo (secondes) |
| `boot_sound` | str/Sound | None | Son pendant l'art ASCII |
| `beep_sound` | str/Sound | None | Son immédiat après confirmation |
| `typing_sound` | str/Sound | None | Son pendant le défilement |
| `loading_sound` | str/Sound | None | Son pendant la barre de chargement |
| `final_sound` | str/Sound | None | Son final |
| `loading_duration` | int | 5 | Durée barre de chargement (secondes) |
| `scroll_delay` | float | 0.10 | Pause entre les lignes (secondes) |
| `prompt` | str | "BOOT ? (Y/N) : " | Texte du prompt |
| `confirm_key` | str | "Y" | Touche de confirmation |
| `cancel_key` | str | "N" | Touche d'annulation |

### Menu

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `header` | str | "" | Titre ligne 1 |
| `subheader` | str | "" | Titre ligne 2 |
| `footer` | str | "[ENTER QUERY]" | Invite de saisie |
| `header_prefix` | str | "# - " | Préfixe du header |
| `typing_sound` | str/Sound | None | Son pendant l'affichage des choix |
| `menu_row_start` | int | 7 | Première ligne des choix |
| `choice_indent` | int | 4 | Colonne de départ des choix |
| `choice_format` | str | "{key} - {label}" | Format d'une ligne de choix |
| `unknown_msg` | str | "[?] Commande inconnue : {key}" | Message si touche invalide |

### SplitMenu

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `header` | str | "TERMINAL" | Titre du terminal |
| `folder_label` | str | "FOLDERS" | Étiquette colonne gauche |
| `exit_key` | str | "Q" | Touche de sortie rapide |
| `footer` | str | None | Footer (auto si None) |
| `typing_sound` | str/Sound | None | Son pendant l'affichage |
| `response_delay` | float | 0.12 | Pause entre les lignes de TextPage |
| `key_up/down/open/back/enter` | bytes | flèches ANSI | Touches de navigation |
| `nav_navigate/open/back/play/quit` | str | — | Labels de navigation dans le footer |

### TextPage

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `path` | str | — | Chemin du fichier |
| `typing_sound` | str/Sound | None | Son pendant l'écriture |
| `scroll_delay` | float | 0.12 | Pause entre les lignes |
| `header` | str | nom du fichier | Header de page |
| `footer_next` | str | "[SUITE. Appuyez ENTREE]" | Footer suite |
| `footer_end` | str | "[FIN. Appuyez ENTREE]" | Footer fin |

### LLMTerminal

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `name` | str | — | Nom de l'IA |
| `header` | str | name | Titre du terminal |
| `input_prompt` | str | name | Texte avant la zone de saisie |
| `prompt` / `prompt_file` | str | — | System prompt LLM |
| `provider` | str | "openai" | "openai" / "anthropic" / "ollama" |
| `model` | str | "gpt-4o-mini" | Identifiant du modèle |
| `sounds["typing"]` | str/Sound | None | Son pendant la réponse |
| `sounds["thinking"]` | str/Sound | None | Son pendant l'attente |
| `exit_command` | str | "/exit" | Commande de sortie |
| `response_delay` | float | 0.02 | Pause entre les lignes de réponse |
| `boot_prompt` | str | None | Prompt de confirmation boot |
| `boot_confirm` | str | "Y" | Touche de confirmation boot |
| `boot_logo` | str | None | Fichier logo de boot |
| `boot_sound` | str/Sound | None | Son pendant le logo de boot |
| `boot_scroll_delay` | float | 0.10 | Vitesse du défilement du logo |
| `label_you` | str | "[YOU]" | Étiquette utilisateur |
| `label_thinking` | str | "THINKING..." | Texte d'attente LLM |
| `error_prefix` | str | "[SYSTEM ERROR]" | Préfixe erreurs |

---

## Providers LLM

| Provider | `provider=` | Clé API | Notes |
|----------|-------------|---------|-------|
| OpenAI | `"openai"` | `OPENAI_API_KEY` | Tool use natif |
| Anthropic | `"anthropic"` | `ANTHROPIC_API_KEY` | Tool use + prompt cache |
| Ollama | `"ollama"` | — | Local, commandes `[SET]` seulement |

```python
# Clé API directement dans le code (déconseillé, préférer .env)
LLMTerminal(..., api_key="sk-...")

# URL Ollama personnalisée
LLMTerminal(..., provider="ollama", base_url="http://192.168.1.10:11434")
```

---

## Persistance et reset

```python
campaign = Campaign(
    device    = args.device,
    save_file = "ma_campagne.json",   # None = pas de persistance
)
```

```bash
# Effacer la sauvegarde depuis la ligne de commande :
python campaigns/ma_campagne.py --reset
```

---

## Mode debug

```bash
python campaigns/exemple.py --debug
```

Ou dans le code :
```python
campaign = Campaign(debug=True)
```

---

## Démarrage automatique sur Raspberry Pi

Pour que la campagne se lance automatiquement au démarrage du Pi (sans intervention manuelle), on crée un service systemd.

### 1. Créer le fichier de service

```bash
sudo nano /etc/systemd/system/minitelrpg.service
```

Contenu :

```ini
[Unit]
Description=MinitelRPG — SEVASTOLINK
After=network.target

[Service]
Type=simple
User=muthur
WorkingDirectory=/home/muthur/MinitelRPG-framework
EnvironmentFile=/home/muthur/MinitelRPG-framework/.env
ExecStart=/home/muthur/MinitelRPG-framework/venv/bin/python campaigns/sevastolink.py --device /dev/ttyUSB0 --baud 4800
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> Adapter `User`, `WorkingDirectory` et `ExecStart` si votre projet est dans un autre dossier.

### 2. Activer et démarrer le service

```bash
sudo systemctl daemon-reload
sudo systemctl enable minitelrpg
sudo systemctl start minitelrpg
```

### 3. Commandes utiles

```bash
# Vérifier que le service tourne
sudo systemctl status minitelrpg

# Voir les logs en direct
journalctl -u minitelrpg -f

# Redémarrer le service
sudo systemctl restart minitelrpg

# Arrêter le service
sudo systemctl stop minitelrpg

# Désactiver le démarrage automatique
sudo systemctl disable minitelrpg
```

> `Restart=on-failure` avec `RestartSec=5` : si le script plante, il redémarre automatiquement après 5 secondes.

### Note sur le Minitel

Le framework détecte automatiquement si le Minitel est éteint au démarrage et attend qu'il soit allumé avant de continuer. Il n'est donc pas nécessaire que le Minitel soit allumé avant le Pi.
