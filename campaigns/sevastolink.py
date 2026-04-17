# -*- coding: utf-8 -*-
"""
campaigns/sevastolink.py

Campagne "Destroyer of Worlds" pour Alien RPG.
Exemple complet montrant toutes les fonctionnalités du framework.

Lancement :
    python campaigns/sevastolink.py
    python campaigns/sevastolink.py --device /dev/ttyUSB0 --baud 4800
"""

import argparse
import os
import sys


# --- Ajouter le dossier parent au path si lancé directement ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import (
    Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction, MenuExit, Sound, SplitMenu, AudioItem
)

# ---------------------------------------------------------------------------
# Chemins des assets (relatifs à ce fichier)
# ---------------------------------------------------------------------------
HERE   = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets", "sevastolink")
SOUNDS = os.path.join(ASSETS, "sounds")

def asset(name: str) -> str:
    return os.path.join(ASSETS, name)

def sound(name: str) -> str:
    return os.path.join(SOUNDS, name)


# ---------------------------------------------------------------------------
# Interface LLM : APOLLO
# ---------------------------------------------------------------------------
apollo = LLMTerminal(
    name         = "A.P.O.L.L.O",
    header       = "#  -  A.P.O.L.L.O -                       CENTRAL ARTIFICIAL INTELLIGENCE",
    input_prompt = "ENTER QUERY",
    prompt_file  = asset("prompt_sevastolink.txt"),
    provider     = "openai",
    model        = "gpt-5-mini",
    sounds       = {
        "typing":   Sound(sound("typing_long.wav"), volume=0.4),
        "thinking": Sound(sound("thinking.wav"), volume=0.4),
    },
    boot_prompt  = "INITIALISER A.P.O.L.L.O ? (Y/N) : ",
    boot_logo    = asset("logo-seegson.txt"),
    boot_sound   = sound("typing_long.wav"),
    exit_command = "/exit",
)

# ---------------------------------------------------------------------------
# Interface LLM : MU/TH/UR
# ---------------------------------------------------------------------------
muthur = LLMTerminal(
    name        = "MU/TH/UR 6000",
    header      = "WEYLAND-YUTANI MAINFRAME — MU/TH/UR 6000",
    prompt_file = asset("prompt_muthur.txt"),
    provider    = "anthropic",
    model       = "claude-opus-4-5",
    sounds      = {
        "typing":   sound("typing_long.wav"),
        "thinking": sound("thinking.wav"),
    },
    exit_command = "/exit",
)


# ---------------------------------------------------------------------------
# Sous-menu : PROTOCOLE DE CONFINEMENT
# ---------------------------------------------------------------------------
containment_menu = Menu(
    header       = "CONTAINMENT PROTOCOL",
    subheader    = "EMERGENCY PROCEDURES",
    typing_sound = sound("typing_long.wav"),
)

containment_menu.add_choice(
    "1", "ISOLER SECTION C",
    action = CallbackAction(lambda term, state: (
        state.update({"section_c_locked": True}),
        term.at(12, 4, ">>> SECTION C VERROUILLÉE <<<"),
        term.wait_enter(),
    ))
)

containment_menu.add_choice(
    "2", "PURGE ATMOSPHÉRIQUE",
    action = CallbackAction(lambda term, state: (
        state.update({"purge_done": True, "contamination": False}),
        term.at(12, 4, ">>> PURGE INITIÉE. CONTAMINATION NEUTRALISÉE <<<"),
        term.wait_enter(),
    ))
)

containment_menu.add_choice(
    "3", "RETOUR",
    action = CallbackAction(lambda term, state: (_ for _ in ()).throw(MenuExit()))
)


# ---------------------------------------------------------------------------
# SplitMenu : terminal personnel style Alien Isolation
# ---------------------------------------------------------------------------
personal_terminal = SplitMenu(
    header       = "PERSONAL TERMINAL",
    folder_label = "FOLDERS",
    exit_key     = "Q",
    typing_sound = sound("typing_long.wav"),
)

personal_folder = SplitMenu(
    header       = "PERSONAL TERMINAL",
    folder_label = "PERSONAL",
)

personal_folder.add_item("MAIL",
    action=TextPage(asset("mail.txt"),
    typing_sound=sound("typing_long.wav")))
personal_terminal.add_item("PERSONAL", action=personal_folder)

audio_folder = SplitMenu(
    header       = "PERSONAL TERMINAL",
    folder_label = "AUDIO",
)
audio_folder.add_item("LOG 01 - MARLOW",
    action = AudioItem(sound("horn.wav"), description="Personal log - D. Marlow"))
audio_folder.add_item("LOG 02 - VERLAINE",
    action = AudioItem(sound("exemple.wav"), description="Personal log - A. Verlaine"))
personal_terminal.add_item("AUDIO", action=audio_folder)

personal_terminal.add_item("A.P.O.L.L.O", action=apollo,
    condition = lambda state: state.get("apollo_unlocked", True))


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Événements d'état
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Séquence de boot
# ---------------------------------------------------------------------------
boot = Boot(
    art                   = asset("art.txt"),
    logo                  = asset("logo.txt"),
    logo_display_duration = 5.0,
    scroll_text           = asset("boot.txt"),
    boot_sound       = Sound(sound("exemple.wav"), volume=1),
    beep_sound       = sound("beep.wav"),
    typing_sound     = Sound(sound("typing_long.wav"), volume=0.3),
    loading_sound    = Sound(sound("subtle_long_type.wav"), volume=0.3),
    final_sound      = sound("horn.wav"),
    loading_duration = 6,
    scroll_delay     = 0.1,
    prompt           = "               BOOT ? (Y/N) : ",
)


# ---------------------------------------------------------------------------
# Campagne
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Sevastolink — Alien RPG")
    parser.add_argument("--device",  default="/dev/ttyUSB0")
    parser.add_argument("--baud",    type=int, default=4800)
    parser.add_argument("--term",    default=None)
    parser.add_argument("--save",    default="sevastolink_save.json",
                        help="Fichier de sauvegarde de l'état de session")
    parser.add_argument("--no-save", action="store_true",
                        help="Désactiver la persistance entre sessions")
    parser.add_argument("--reset",   action="store_true",
                        help="Effacer la sauvegarde et repartir de zéro")
    parser.add_argument("--debug",   action="store_true",
                        help="Mode debug : terminal Linux, sans Minitel")
    args = parser.parse_args()

    save_file = None if args.no_save else args.save

    if args.reset and save_file and os.path.isfile(save_file):
        os.remove(save_file)
        print(f"[reset] Sauvegarde supprimée : {save_file}")

    campaign = Campaign(
        device       = args.device,
        baud         = args.baud,
        termname     = args.term,
        save_file    = save_file,
        loop_on_exit = True,
        debug        = args.debug,
    )
    campaign.boot = boot
    campaign.menu = personal_terminal
    campaign.run()


if __name__ == "__main__":
    main()
