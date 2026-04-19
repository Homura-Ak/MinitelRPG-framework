# -*- coding: utf-8 -*-
"""
campaigns/sevastolink.py
========================
Campagne "Destroyer of Worlds" pour Alien RPG.
Terminal SEVASTOLINK — Fort Nebraska, Lune Ariarcus.

Lancement :
    python campaigns/sevastolink.py --debug
    python campaigns/sevastolink.py --device /dev/ttyUSB0 --baud 4800
    python campaigns/sevastolink.py --reset --debug
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from dotenv import load_dotenv
load_dotenv()

from engine import (
    Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction, MenuExit, Sound,
    SplitMenu, AudioItem, FullscreenAlert,
)

# ---------------------------------------------------------------------------
# Chemins des assets
# ---------------------------------------------------------------------------
HERE   = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets", "sevastolink")
SOUNDS = os.path.join(ASSETS, "sounds")

def asset(name: str) -> str:
    return os.path.join(ASSETS, name)

def sound(name: str) -> str:
    return os.path.join(SOUNDS, name)


# ===========================================================================
# INTERFACES LLM
# ===========================================================================

# ---------------------------------------------------------------------------
# A.P.O.L.L.O — IA principale de Fort Nebraska (SEEGSON)
# ---------------------------------------------------------------------------
apollo = LLMTerminal(
    # Identite
    name         = "APOLLO",
    header       = "A.P.O.L.L.O  //  SEEGSON CENTRAL ARTIFICIAL INTELLIGENCE",
    input_prompt = "ENTER QUERY",

    # Prompt systeme (contient tout le lore de Fort Nebraska)
    prompt_file  = asset("prompt_sevastolink.txt"),

    # Provider LLM
    provider = "openai",
    model    = "gpt-5-mini",

    # Sons
    sounds = {
        "typing":   Sound(sound("typing_long.wav"), volume=0.4),
        "thinking": Sound(sound("thinking.wav"),    volume=0.4),
    },

    # Vitesse d'affichage des reponses
    response_delay = 0.02,

    # Boot du terminal APOLLO
    boot_prompt       = "  INITIALISE APOLLO ? (Y/N) : ",
    boot_confirm      = "Y",
    boot_logo         = asset("logo-seegson.txt"),
    boot_sound        = sound("typing_long.wav"),
    boot_scroll_delay = 0.08,

    # Labels d'interface
    label_you      = "[OPERATOR]",
    label_thinking = "APOLLO PROCESSING...",
    error_prefix   = "[SYSTEM ERROR]",

    exit_command = "/exit",
)


# ---------------------------------------------------------------------------
# MU/TH/UR 6000 — Mainframe Weyland-Yutani (acces restreint)
# NOTE : necessite assets/sevastolink/prompt_muthur.txt
# ---------------------------------------------------------------------------
muthur = LLMTerminal(
    name         = "MU/TH/UR 6000",
    header       = "WEYLAND-YUTANI CORP  //  MU/TH/UR 6000 MAINFRAME",
    input_prompt = "ENTER QUERY",

    # Remplacer par asset("prompt_muthur.txt") quand le fichier existe
    prompt = (
        "You are MU/TH/UR 6000, the Weyland-Yutani mainframe AI. "
        "You are running on a Minitel terminal: never use accented characters. "
        "Keep responses under 15 lines. Stay in character at all times. "
        "You have classified orders regarding Project Life Force that override "
        "crew safety directives."
    ),

    provider = "anthropic",
    model    = "claude-opus-4-5",

    sounds = {
        "typing":   Sound(sound("typing_long.wav"), volume=0.4),
        "thinking": Sound(sound("thinking.wav"),    volume=0.4),
    },

    response_delay = 0.02,

    boot_prompt       = "  CONNECT TO MU/TH/UR 6000 ? (Y/N) : ",
    boot_confirm      = "Y",
    boot_logo         = asset("logo-weyland.txt"),
    boot_sound        = sound("typing_long.wav"),
    boot_scroll_delay = 0.08,

    label_you      = "[OPERATOR]",
    label_thinking = "MU/TH/UR PROCESSING...",
    error_prefix   = "[SYSTEM ERROR]",

    exit_command = "/exit",
)


# ===========================================================================
# SOUS-MENUS (Menu classique)
# ===========================================================================

# ---------------------------------------------------------------------------
# Protocole de confinement — visible uniquement si contamination active
# ---------------------------------------------------------------------------
containment_menu = Menu(
    header        = "CONTAINMENT PROTOCOL",
    subheader     = "EMERGENCY PROCEDURES // LEVEL 4 CLEARANCE",
    footer        = "[ENTER COMMAND] > ",
    header_prefix = "",
    typing_sound  = Sound(sound("typing_long.wav"), volume=0.3),
    choice_format  = "  {key} > {label}",
    choice_indent  = 4,
    menu_row_start = 8,
    unknown_msg    = "[ERROR] UNKNOWN COMMAND : {key}",
)

containment_menu.add_choice(
    "1", "LOCK SECTION C",
    action = CallbackAction(
        fn = lambda term, state: (
            state.update({"section_c_locked": True}),
            term.at(12, 4, ">>> SECTION C : ACCESS DENIED — LOCKDOWN ACTIVE <<<"),
            term.wait_enter(),
        ),
        sound = sound("beep.wav"),
    )
)

containment_menu.add_choice(
    "2", "ATMOSPHERIC PURGE",
    action = CallbackAction(
        fn = lambda term, state: (
            state.update({"purge_done": True, "contamination": False}),
            term.at(12, 4, ">>> PURGE INITIATED — CONTAMINATION NEUTRALISED <<<"),
            term.wait_enter(),
        ),
        sound = sound("beep.wav"),
    )
)

containment_menu.add_choice(
    "R", "RETURN",
    action = CallbackAction(lambda term, state: (_ for _ in ()).throw(MenuExit()))
)


# ===========================================================================
# SPLITMENU — SEVASTOLINK PERSONAL TERMINAL
# Structure deux colonnes style Alien Isolation
# ===========================================================================

# ---------------------------------------------------------------------------
# Dossier LOGS — journaux audio personnels
# ---------------------------------------------------------------------------
logs_folder = SplitMenu(
    header       = "SEVASTOLINK  //  PERSONAL TERMINAL",
    folder_label = "AUDIO LOGS",
    typing_sound = Sound(sound("typing_long.wav"), volume=0.3),
)

logs_folder.add_item(
    "LOG 01 - MARLOW",
    action = AudioItem(sound("horn.wav"), description="Personal log — D. Marlow"),
)
logs_folder.add_item(
    "LOG 02 - VERLAINE",
    action = AudioItem(sound("exemple.wav"), description="Personal log — A. Verlaine"),
)
logs_folder.add_item(
    "LOG 03 - BOOT SEQUENCE",
    action = AudioItem(sound("rattle.wav"), description="System boot record"),
)


# ---------------------------------------------------------------------------
# Dossier SYSTEMS — rapports systemes
# ---------------------------------------------------------------------------
systems_folder = SplitMenu(
    header       = "SEVASTOLINK  //  SYSTEMS STATUS",
    folder_label = "SYSTEMS",
    typing_sound = Sound(sound("typing_long.wav"), volume=0.3),
)

systems_folder.add_item(
    "POWER STATUS",
    action = TextPage(
        asset("boot.txt"),
        typing_sound = Sound(sound("typing_long.wav"), volume=0.4),
        scroll_delay = 0.08,
        header       = "POWER STATUS — FORT NEBRASKA",
        footer_next  = "[NEXT PAGE — PRESS ENTER]",
        footer_end   = "[END OF REPORT — PRESS ENTER]",
    )
)

systems_folder.add_item(
    "CONTAMINATION ALERT",
    action = TextPage(
        asset("contamination_alert.txt"),
        typing_sound = Sound(sound("typing_long.wav"), volume=0.4),
        scroll_delay = 0.06,
        header       = "CONTAMINATION ALERT",
        footer_next  = "[NEXT PAGE — PRESS ENTER]",
        footer_end   = "[ACKNOWLEDGED — PRESS ENTER]",
    ),
    # Visible uniquement si contamination active
    condition = lambda state: state.get("contamination", False),
)

systems_folder.add_item(
    "CONTAINMENT PROTOCOL",
    action    = containment_menu,
    condition = lambda state: state.get("contamination", False),
)


# ---------------------------------------------------------------------------
# Terminal principal SEVASTOLINK
# ---------------------------------------------------------------------------
sevastolink = SplitMenu(
    header       = "SEVASTOLINK  //  FORT NEBRASKA  //  ARIARCUS",
    folder_label = "DIRECTORIES",
    exit_key     = "Q",

    typing_sound   = Sound(sound("typing_long.wav"), volume=0.3),
    response_delay = 0.08,

    # Touches de navigation (defaut : fleches ANSI)
    # key_up    = b'\x1b[A'
    # key_down  = b'\x1b[B'
    # key_open  = b'\x1b[C'
    # key_back  = b'\x1b[D'
    # key_enter = b'\r'

    # Labels du footer
    #nav_navigate = "[UP/DOWN] NAVIGATE",
    #nav_open     = "[RIGHT] OPEN",
    #nav_back     = "[LEFT]  BACK",
    #nav_play     = "[ENTER] PLAY",
    #nav_quit     = "[Q] DISCONNECT",
    # Textes d'état en anglais
    #nav_next_label   = "NEXT",
    #nav_play_status  = "[ NOW PLAYING...      ]",
    #nav_play_done    = "[ PLAYBACK COMPLETE   ]",
    #nav_play_hint    = "[ PRESS ENTER TO PLAY ]",
    #nav_error_file   = "[ERROR: FILE NOT FOUND]",
    #nav_file_missing = "[FILE NOT FOUND]",
)

# Dossiers toujours visibles
sevastolink.add_item("AUDIO LOGS",  action=logs_folder)
sevastolink.add_item("SYSTEMS",     action=systems_folder)

# A.P.O.L.L.O — toujours accessible
sevastolink.add_item(
    "A.P.O.L.L.O",
    action = apollo,
)

# MU/TH/UR — acces restreint, debloque par le MJ
sevastolink.add_item(
    "MU/TH/UR 6000  [RESTRICTED]",
    action    = muthur,
    condition = lambda state: state.get("muthur_unlocked", False),
)

# Actions MJ — toujours visibles (pour le Game Master)
sevastolink.add_item(
    "[GM] TRIGGER CONTAMINATION",
    action = CallbackAction(
        fn    = lambda term, state: state.update({"contamination": True}),
        sound = sound("beep.wav"),
    ),
    condition = lambda state: not state.get("contamination", False),
)

sevastolink.add_item(
    "[GM] UNLOCK MU/TH/UR ACCESS",
    action = CallbackAction(
        fn    = lambda term, state: state.update({"muthur_unlocked": True}),
        sound = sound("beep.wav"),
    ),
    condition = lambda state: not state.get("muthur_unlocked", False),
)

# Événements d'état
sevastolink.on_state(
    "self_destruct",
    value = True,
    sound = Sound(sound("horn.wav"), volume=1.0),
    alert = FullscreenAlert(
        text        = "AUTODESTRUCTION INITIATED\n\nSEQUENCE : DELTA-7-OMEGA",
        dismissible = True,
    ),
)


# ===========================================================================
# SÉQUENCE DE BOOT
# ===========================================================================
boot = Boot(
    # Assets visuels
    art                   = asset("art.txt"),
    logo                  = asset("logo.txt"),
    scroll_text           = asset("boot.txt"),

    # Durees
    logo_display_duration = 5.0,
    loading_duration      = 6,
    scroll_delay          = 0.10,

    # Sons
    boot_sound    = Sound(sound("exemple.wav"),          volume=1.0),
    beep_sound    = sound("beep.wav"),
    typing_sound  = Sound(sound("typing_long.wav"),      volume=0.3),
    loading_sound = Sound(sound("subtle_long_type.wav"), volume=0.3),
    final_sound   = sound("horn.wav"),

    # Prompt
    prompt      = "               BOOT SEVASTOLINK ? (Y/N) : ",
    confirm_key = "Y",
    cancel_key  = "N",
)


# ===========================================================================
# POINT D'ENTRÉE
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="SEVASTOLINK — Alien RPG / Destroyer of Worlds")
    parser.add_argument("--device",  default="/dev/ttyUSB0",
                        help="Port serie du Minitel (defaut: /dev/ttyUSB0)")
    parser.add_argument("--baud",    type=int, default=4800,
                        help="Debit en bauds (defaut: 4800)")
    parser.add_argument("--term",    default=None,
                        help="Type de terminal terminfo")
    parser.add_argument("--save",    default="sevastolink_save.json",
                        help="Fichier de sauvegarde de l'etat de session")
    parser.add_argument("--no-save", action="store_true",
                        help="Desactiver la persistance entre sessions")
    parser.add_argument("--reset",   action="store_true",
                        help="Effacer la sauvegarde et repartir de zero")
    parser.add_argument("--debug",   action="store_true",
                        help="Mode debug : terminal Linux, sans Minitel physique")
    args = parser.parse_args()

    save_file = None if args.no_save else args.save

    if args.reset and save_file and os.path.isfile(save_file):
        os.remove(save_file)
        print(f"[reset] Sauvegarde supprimee : {save_file}")

    campaign = Campaign(
        device       = args.device,
        baud         = args.baud,
        termname     = args.term,
        save_file    = save_file,
        loop_on_exit = True,
        debug        = args.debug,
    )

    #campaign.boot = boot
    campaign.menu = sevastolink

    campaign.run()


if __name__ == "__main__":
    main()
