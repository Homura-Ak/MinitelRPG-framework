# -*- coding: utf-8 -*-
"""
campaigns/exemple.py
====================
Campagne d'exemple complète — Alien RPG "Destroyer of Worlds".

Ce fichier est le point de départ recommandé pour créer votre propre campagne.
Il illustre toutes les fonctionnalités du framework avec des commentaires détaillés.

Lancement :
    python campaigns/exemple.py --debug             # test sans Minitel
    python campaigns/exemple.py --device /dev/ttyUSB0 --baud 4800
    python campaigns/exemple.py --reset --debug     # repart de zéro
"""

import argparse
import os
import sys

# Ajoute le dossier parent au path pour l'import des modules engine
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import (
    Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction, MenuExit, Sound,
    SplitMenu, AudioItem,
)

# ---------------------------------------------------------------------------
# Chemins des assets
# Toujours utiliser des chemins absolus pour éviter les problèmes de CWD.
# ---------------------------------------------------------------------------
HERE   = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets", "exemple")
SOUNDS = os.path.join(ASSETS, "sounds")

def asset(name: str) -> str:
    """Retourne le chemin absolu d'un fichier dans le dossier assets."""
    return os.path.join(ASSETS, name)

def sound(name: str) -> str:
    """Retourne le chemin absolu d'un fichier dans le dossier sounds."""
    return os.path.join(SOUNDS, name)


# ===========================================================================
# INTERFACES LLM
# ===========================================================================

# ---------------------------------------------------------------------------
# A.P.O.L.L.O — IA principale de la base
# ---------------------------------------------------------------------------
# Toutes les options sont commentées pour montrer ce qui est personnalisable.
apollo = LLMTerminal(
    # --- Identité ---
    name         = "A.P.O.L.L.O",
    header       = "#  -  A.P.O.L.L.O -                       CENTRAL ARTIFICIAL INTELLIGENCE",
    input_prompt = "ENTER QUERY",       # texte devant la zone de saisie

    # --- Prompt système ---
    # prompt_file = chemin vers un fichier .txt (recommandé pour les longs prompts)
    # prompt      = "texte direct" (pour les prompts courts)
    prompt_file  = asset("prompt_apollo.txt"),

    # --- Provider LLM ---
    provider = "openai",
    model    = "gpt-4o-mini",
    # api_key = "sk-..."  # si non défini, lue depuis OPENAI_API_KEY

    # --- Sons ---
    sounds = {
        # "typing"   : joué en boucle pendant l'affichage de la réponse
        # "thinking" : joué en boucle pendant l'attente du LLM
        "typing":   Sound(sound("typing_long.wav"), volume=0.4),
        "thinking": Sound(sound("rattle.wav"),      volume=0.4),
    },

    # --- Commande de sortie ---
    exit_command = "/exit",

    # --- Vitesse d'affichage des réponses ---
    # 0.01 = quasi-instantané, 0.02 = normal, 0.05 = effet machine à écrire lent
    response_delay = 0.02,

    # --- Séquence de boot optionnelle ---
    # Si boot_prompt est défini, l'utilisateur doit confirmer avant d'accéder au terminal.
    boot_prompt       = "INITIALISER A.P.O.L.L.O ? (Y/N) : ",
    boot_confirm      = "Y",
    boot_logo         = asset("logo-seegson.txt"),  # logo défilant après confirmation
    boot_sound        = sound("typing_long.wav"),   # son pendant le défilement du logo
    boot_scroll_delay = 0.10,                       # vitesse du défilement du logo

    # --- Labels d'interface ---
    label_you      = "[YOU]",           # préfixe des questions utilisateur
    label_thinking = "THINKING...",     # affiché pendant le calcul LLM
    error_prefix   = "[SYSTEM ERROR]",  # préfixe des messages d'erreur
)


# ---------------------------------------------------------------------------
# MU/TH/UR 6000 — IA restreinte Weyland-Yutani
# ---------------------------------------------------------------------------
# Exemple avec provider Anthropic et un prompt depuis un fichier
# (décommentez et adaptez si vous avez un fichier prompt_muthur.txt)
#
# muthur = LLMTerminal(
#     name         = "MU/TH/UR 6000",
#     header       = "WEYLAND-YUTANI MAINFRAME — MU/TH/UR 6000",
#     prompt_file  = asset("prompt_muthur.txt"),
#     provider     = "anthropic",
#     model        = "claude-sonnet-4-6",
#     sounds       = {
#         "typing":   Sound(sound("typing_long.wav"), volume=0.4),
#         "thinking": Sound(sound("rattle.wav"),      volume=0.4),
#     },
#     exit_command   = "/exit",
#     response_delay = 0.03,
#     label_thinking = "PROCESSING...",
# )


# ===========================================================================
# SOUS-MENUS
# ===========================================================================

# ---------------------------------------------------------------------------
# Sous-menu : protocole de confinement
# Apparaît uniquement quand la contamination est active (voir menu principal).
# ---------------------------------------------------------------------------
containment_menu = Menu(
    header       = "CONTAINMENT PROTOCOL",
    subheader    = "EMERGENCY PROCEDURES",
    footer       = "[ENTRER COMMANDE] > ",

    # Son joué pendant l'affichage des choix de ce sous-menu
    typing_sound = sound("typing_long.wav"),

    # Format des choix avec indentation custom
    choice_indent  = 6,
    choice_format  = "  {key} > {label}",
    menu_row_start = 8,
)

containment_menu.add_choice(
    "1", "ISOLER SECTION C",
    action = CallbackAction(
        fn = lambda term, state: (
            state.update({"section_c_locked": True}),
            term.at(12, 4, ">>> SECTION C VERROUILLEE <<<"),
            term.wait_enter(),
        ),
        sound = sound("beep.wav"),  # son joué avant l'action
    )
)

containment_menu.add_choice(
    "2", "PURGE ATMOSPHERIQUE",
    action = CallbackAction(
        fn = lambda term, state: (
            state.update({"purge_done": True, "contamination": False}),
            term.at(12, 4, ">>> PURGE INITIEE. CONTAMINATION NEUTRALISEE <<<"),
            term.wait_enter(),
        )
    )
)

containment_menu.add_choice(
    "R", "RETOUR",
    action = CallbackAction(lambda term, state: (_ for _ in ()).throw(MenuExit()))
)


# ===========================================================================
# MENU PRINCIPAL (classique)
# ===========================================================================
main_menu = Menu(
    # Textes d'affichage
    header    = "SEEGSON BIOS 5.3.09.63",
    subheader = "APOLLO STATION — HADLEY'S HOPE",
    footer    = "[ENTER QUERY] > ",

    # Format des choix (ici style par défaut)
    choice_format  = "{key} - {label}",
    choice_indent  = 4,
    menu_row_start = 7,
    header_prefix  = "# - ",

    # Son pendant l'affichage des choix
    typing_sound = sound("typing_long.wav"),

    # Message si touche invalide
    unknown_msg = "[?] Commande inconnue : {key}",
)

# --- Choix toujours visibles ---
main_menu.add_choice("1", "A.P.O.L.L.O",
    action = apollo)

main_menu.add_choice("2", "POWER STATUS",
    action = TextPage(
        asset("2.txt"),
        typing_sound = Sound(sound("typing_long.wav"), volume=0.4),
        scroll_delay = 0.10,
        header       = "POWER STATUS REPORT",
        footer_next  = "[PAGE SUIVANTE — APPUYER SUR ENTREE]",
        footer_end   = "[FIN DU RAPPORT — APPUYER SUR ENTREE]",
    ))

main_menu.add_choice("3", "HVAC",
    action = TextPage(asset("3.txt"),
        typing_sound = sound("typing_long.wav"),
        scroll_delay = 0.08,
    ))

main_menu.add_choice("4", "LIGHTING",
    action = TextPage(asset("4.txt"),
        typing_sound = sound("typing_long.wav"),
    ))

# --- Choix conditionnel : MU/TH/UR uniquement si débloquée ---
# main_menu.add_choice(
#     "M", "MU/TH/UR 6000 [RESTRICTED]",
#     action    = muthur,
#     condition = lambda state: state.get("muthur_unlocked", False),
# )

# --- Choix conditionnel : protocole de confinement si contamination active ---
main_menu.add_choice(
    "5", "CONTAINMENT PROTOCOL [ACTIVE]",
    action    = containment_menu,
    condition = lambda state: state.get("contamination", False),
    # Son spécifique joué quand CE choix est sélectionné
    sounds    = {"select": sound("horn.wav")},
)

# --- Actions GM (Game Master) : toujours visibles mais clairement étiquetées ---
main_menu.add_choice(
    "X", "TRIGGER CONTAMINATION EVENT [GM]",
    action    = CallbackAction(
        fn    = lambda term, state: state.update({"contamination": True}),
        sound = sound("beep.wav"),
    ),
    condition = lambda state: not state.get("contamination", False),
)

main_menu.add_choice(
    "U", "UNLOCK MU/TH/UR ACCESS [GM]",
    action    = CallbackAction(
        lambda term, state: state.update({"muthur_unlocked": True})
    ),
    condition = lambda state: not state.get("muthur_unlocked", False),
)

main_menu.add_choice(
    "Q", "QUITTER",
    action = CallbackAction(lambda term, state: (_ for _ in ()).throw(MenuExit()))
)


# ===========================================================================
# ÉVÉNEMENTS D'ÉTAT
# Ces événements sont déclenchés automatiquement quand l'état change,
# même si c'est le LLM qui a modifié l'état via tool use ou [SET ...].
# ===========================================================================

# Quand contamination passe à True → son d'alerte + écran plein
main_menu.on_state(
    "contamination",
    value        = True,
    sound        = sound("horn.wav"),
    message_file = asset("contamination_alert.txt"),
)

# Quand contamination repasse à False → message court
main_menu.on_state(
    "contamination",
    value   = False,
    sound   = sound("beep.wav"),
    message = "Contamination neutralisee. Retour a la normale.",
)

# Quand MU/TH/UR est débloquée → message d'information
main_menu.on_state(
    "muthur_unlocked",
    value   = True,
    message = "Acces MU/TH/UR 6000 deverrouille.",
)


# ===========================================================================
# SÉQUENCE DE BOOT
# ===========================================================================
boot = Boot(
    # Assets visuels
    art                   = asset("art.txt"),    # affiché sur l'écran du prompt
    logo                  = asset("logo.txt"),   # affiché quelques secondes après confirmation
    scroll_text           = asset("boot.txt"),   # défile entre le logo et la barre de chargement

    # Durées
    logo_display_duration = 5.0,   # secondes d'affichage du logo
    loading_duration      = 2,     # secondes de la barre de chargement
    scroll_delay          = 0.10,  # secondes entre chaque ligne du défilement

    # Sons (str ou Sound pour contrôler le volume)
    boot_sound    = Sound(sound("exemple.wav"),          volume=1.0),
    beep_sound    = sound("beep.wav"),
    typing_sound  = Sound(sound("typing_long.wav"),      volume=0.3),
    loading_sound = Sound(sound("subtle_long_type.wav"), volume=0.3),
    final_sound   = sound("horn.wav"),

    # Prompt de confirmation
    prompt      = "               BOOT ? (Y/N) : ",
    confirm_key = "Y",
    cancel_key  = "N",
)


# ===========================================================================
# EXEMPLE ALTERNATIF : SplitMenu (terminal deux colonnes style Alien Isolation)
# Décommentez pour utiliser à la place de main_menu dans Campaign.
# ===========================================================================

# personal_terminal = SplitMenu(
#     header        = "PERSONAL TERMINAL",
#     folder_label  = "DOSSIERS",
#     exit_key      = "Q",
#     typing_sound  = sound("typing_long.wav"),
#     response_delay = 0.08,
#     # Labels de navigation du footer (tous personnalisables)
#     nav_navigate  = "[HAUT/BAS] NAVIGUER",
#     nav_open      = "[DROITE] OUVRIR",
#     nav_back      = "[GAUCHE] RETOUR",
#     nav_play      = "[ENTREE] JOUER",
#     nav_quit      = "[Q] QUITTER",
# )
#
# personal_folder = SplitMenu(header="PERSONAL TERMINAL", folder_label="PERSO")
# personal_folder.add_item("MAIL", action=TextPage(asset("mail.txt"),
#                                     typing_sound=sound("typing_long.wav")))
# personal_terminal.add_item("PERSONNEL", action=personal_folder)
#
# audio_folder = SplitMenu(header="PERSONAL TERMINAL", folder_label="AUDIO")
# audio_folder.add_item("LOG 01 — MARLOW",
#     action=AudioItem(sound("horn.wav"), description="Journal personnel — D. Marlow"))
# audio_folder.add_item("LOG 02 — VERLAINE",
#     action=AudioItem(sound("exemple.wav"), description="Journal personnel — A. Verlaine"))
# personal_terminal.add_item("AUDIO", action=audio_folder)
#
# personal_terminal.add_item(
#     "A.P.O.L.L.O",
#     action    = apollo,
#     condition = lambda s: s.get("apollo_unlocked", True),
# )


# ===========================================================================
# POINT D'ENTRÉE
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Exemple — MinitelRPG Framework")
    parser.add_argument("--device",  default="/dev/ttyUSB0",
                        help="Port série du Minitel (défaut: /dev/ttyUSB0)")
    parser.add_argument("--baud",    type=int, default=4800,
                        help="Débit en bauds (défaut: 4800)")
    parser.add_argument("--term",    default=None,
                        help="Type de terminal terminfo (défaut: variable MINITEL_TERM)")
    parser.add_argument("--save",    default="exemple_save.json",
                        help="Fichier de sauvegarde de l'état de session")
    parser.add_argument("--no-save", action="store_true",
                        help="Désactiver la persistance entre sessions")
    parser.add_argument("--reset",   action="store_true",
                        help="Effacer la sauvegarde et repartir de zéro")
    parser.add_argument("--debug",   action="store_true",
                        help="Mode debug : terminal Linux, sans Minitel physique")
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
        loop_on_exit = True,    # reboucle sur le boot après /exit du LLM
        debug        = args.debug,
    )

    # Choisissez ici ce que vous voulez utiliser :
    campaign.boot = boot          # décommentez pour activer la séquence de boot
    campaign.menu = main_menu     # menu classique

    # Pour le SplitMenu à la place :
    # campaign.menu = personal_terminal

    campaign.run()


if __name__ == "__main__":
    main()
