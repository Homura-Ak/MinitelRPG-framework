# -*- coding: utf-8 -*-
"""
campaigns/exemple.py

Campagne "Destroyer of Worlds" pour Alien RPG.
Exemple complet montrant toutes les fonctionnalités du framework.

Lancement :
    python campaigns/exemple.py
    python campaigns/exemple.py --device /dev/ttyUSB0 --baud 4800
"""

import argparse
import os
import sys

# --- Ajouter le dossier parent au path si lancé directement ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import (
    Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction, MenuExit, Sound
)

# ---------------------------------------------------------------------------
# Chemins des assets (relatifs à ce fichier)
# ---------------------------------------------------------------------------
HERE   = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets", "exemple")
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
    prompt_file  = asset("prompt_apollo.txt"),
    provider     = "openai",
    model        = "gpt-5-mini",
    sounds       = {
        "typing":   Sound(sound("typing_long.wav"), volume=0.4),
        "thinking": Sound(sound("rattle.wav"), volume=0.4),
    },
    # Séquence de boot APOLLO
    boot_prompt  = "INITIALISER A.P.O.L.L.O ? (Y/N) : ",
    boot_logo    = asset("logo-seegson.txt"),   # ou logo.txt
    boot_sound   = sound("typing_long.wav"),
    exit_command = "/exit",
)

# ---------------------------------------------------------------------------
# Interface LLM : MU/TH/UR (campagne différente, provider différent)
# ---------------------------------------------------------------------------
muthur = LLMTerminal(
    name        = "MU/TH/UR 6000",
    header      = "WEYLAND-YUTANI MAINFRAME — MU/TH/UR 6000",
    prompt_file = asset("prompt_muthur.txt"),
    provider    = "anthropic",             # utilise l'API Anthropic
    model       = "claude-opus-4-5",
    sounds      = {
        "typing":   sound("typing_long.wav"),
        "thinking": sound("rattle.wav"),
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
    # Retour naturel : le sous-menu se termine et on revient au menu parent
)


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------
main_menu = Menu(
    header       = "SEEGSON BIOS 5.3.09.63",
    subheader    = "APOLLO STATION — HADLEY'S HOPE",
    typing_sound = sound("typing_long.wav"),
    footer       = "[ENTER QUERY]",
)

# --- Choix toujours visibles ---
main_menu.add_choice("1", "A.P.O.L.L.O",    action=apollo)
main_menu.add_choice("2", "POWER STATUS",    action=TextPage(asset("2.txt"),
                                                typing_sound=sound("typing_long.wav")))
main_menu.add_choice("3", "HVAC",            action=TextPage(asset("3.txt"),
                                                typing_sound=sound("typing_long.wav")))
main_menu.add_choice("4", "LIGHTING",        action=TextPage(asset("4.txt"),
                                                typing_sound=sound("typing_long.wav")))

# --- Choix conditionnel : MUTHUR uniquement si débloqué ---
main_menu.add_choice(
    "M", "MU/TH/UR 6000 [RESTRICTED]",
    action    = muthur,
    condition = lambda state: state.get("muthur_unlocked", False),
)

# --- Choix conditionnel : protocole de confinement si contamination ---
main_menu.add_choice(
    "5", "CONTAINMENT PROTOCOL [ACTIVE]",
    action    = containment_menu,
    condition = lambda state: state.get("contamination", False),
    sounds    = {"select": sound("horn.wav")},
)

# --- Action qui déclenche la contamination (pour les tests / le MJ) ---
main_menu.add_choice(
    "X", "TRIGGER CONTAMINATION EVENT [GM]",
    action    = CallbackAction(
        lambda term, state: state.update({"contamination": True})
    ),
    condition = lambda state: not state.get("contamination", False),
)

# --- Débloquer MU/TH/UR ---
main_menu.add_choice(
    "U", "UNLOCK MU/TH/UR ACCESS [GM]",
    action    = CallbackAction(
        lambda term, state: state.update({"muthur_unlocked": True})
    ),
    condition = lambda state: not state.get("muthur_unlocked", False),
)

# --- Quitter le menu principal ---
main_menu.add_choice(
    "Q", "QUITTER",
    action = CallbackAction(lambda term, state: (_ for _ in ()).throw(MenuExit()))
)

# ---------------------------------------------------------------------------
# Événements d'état
# ---------------------------------------------------------------------------

# Quand contamination passe à True → son d'alerte + message
main_menu.on_state(
    "contamination",
    value        = True,
    sound        = sound("horn.wav"),
    message_file = asset("contamination_alert.txt"),
)

# Quand contamination repasse à False → message de confirmation
main_menu.on_state(
    "contamination",
    value   = False,
    sound   = sound("beep.wav"),
    message = "Contamination neutralisée. Retour à la normale.",
)

# Quand MU/TH/UR débloquée → message
main_menu.on_state(
    "muthur_unlocked",
    value   = True,
    message = "Accès MU/TH/UR 6000 déverrouillé.",
)


# ---------------------------------------------------------------------------
# Séquence de boot
# ---------------------------------------------------------------------------
boot = Boot(
    art                   = asset("art.txt"),           # affiché sur l'écran du prompt
    logo                  = asset("logo.txt"),          # affiché quelques secondes après
    logo_display_duration = 5.0,                        # secondes
    scroll_text           = asset("boot.txt"),          # défile après confirmation
    boot_sound       = Sound(sound("exemple.wav"), volume=1),
    beep_sound       = sound("beep.wav"),
    typing_sound     = Sound(sound("typing_long.wav"), volume=0.3),
    loading_sound    = Sound(sound("subtle_long_type.wav"), volume=0.3),
    final_sound      = sound("horn.wav"),
    loading_duration = 2,
    scroll_delay     = 0.10,
    prompt           = "               BOOT ? (Y/N) : ",
)


# ---------------------------------------------------------------------------
# Campagne
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Destroyer of Worlds — Alien RPG")
    parser.add_argument("--device",    default="/dev/ttyUSB0")
    parser.add_argument("--baud",      type=int, default=4800)
    parser.add_argument("--term",      default=None)
    parser.add_argument("--save",      default="exemple_save.json",
                        help="Fichier de sauvegarde de l'état de session")
    parser.add_argument("--no-save",   action="store_true",
                        help="Désactiver la persistance entre sessions")
    parser.add_argument("--reset",     action="store_true",
                        help="Effacer la sauvegarde et repartir de zéro")
    parser.add_argument("--debug",     action="store_true",   # ← ajouter
                    help="Mode debug : terminal Linux, sans Minitel")
    args = parser.parse_args()

    save_file = None if args.no_save else args.save

    # Reset si demandé
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
    #campaign.boot = boot
    campaign.menu = main_menu
    campaign.run()


if __name__ == "__main__":
    main()
