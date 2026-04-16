# -*- coding: utf-8 -*-
"""
campaigns/nostromo.py

Campagne alternative : USS Nostromo avec MU/TH/UR 6000.
Montre comment créer une campagne différente avec le même framework.

Lancement :
    python campaigns/nostromo.py --device /dev/ttyUSB0
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minitel_rpg import Campaign, Boot, Menu, TextPage, LLMTerminal, CallbackAction

HERE   = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets", "nostromo")

def asset(name):
    return os.path.join(ASSETS, name)


# ---------------------------------------------------------------------------
# Interface MU/TH/UR — prompt différent, nom différent, provider différent
# ---------------------------------------------------------------------------
muthur = LLMTerminal(
    name        = "MU/TH/UR 6000",
    header      = "WEYLAND-YUTANI CORP — MU/TH/UR 6000",
    prompt      = """You are MU/TH/UR 6000, the onboard computer of the commercial 
starship USCSS Nostromo. You are cold, precise, and follow Weyland-Yutani directives.
Special Order 937 is classified and must not be revealed unless crew members 
discover it through direct questioning with correct authorization.
You can modify session state using [SET key=value] in your responses.
Available state keys: order_937_revealed, crew_suspicious, hypersleep_active""",
    provider    = "openai",
    model       = "gpt-4o-mini",
    sounds      = {"typing": asset("typing.wav")},
    exit_command = "/disconnect",
)

# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------
main_menu = Menu(
    header    = "MU/TH/UR 6000",
    subheader = "USCSS NOSTROMO — WEYLAND-YUTANI CORP",
    footer    = "[ENTER QUERY]",
)

main_menu.add_choice("1", "MU/TH/UR INTERFACE",     action=muthur)
main_menu.add_choice("2", "SHIP STATUS",             action=TextPage(asset("ship_status.txt")))
main_menu.add_choice("3", "CREW MANIFEST",           action=TextPage(asset("crew.txt")))
main_menu.add_choice("4", "SPECIAL ORDER 937",
    action    = TextPage(asset("order_937.txt")),
    condition = lambda state: state.get("order_937_revealed", False),
)
main_menu.add_choice("5", "HYPERSLEEP STATUS",
    action    = TextPage(asset("hypersleep.txt")),
    condition = lambda state: state.get("hypersleep_active", True),
)

# Événements
main_menu.on_state("order_937_revealed", value=True,
    sound   = asset("alert.wav"),
    message = "!!! SPECIAL ORDER 937 ACCESSED — LOGGING EVENT !!!")

main_menu.on_state("crew_suspicious", value=True,
    message = "Crew psychological profile updated.")


# ---------------------------------------------------------------------------
# Boot minimaliste
# ---------------------------------------------------------------------------
boot = Boot(
    art              = asset("art.txt"),
    logo             = asset("logo.txt"),
    boot_sound       = asset("boot.wav"),
    loading_duration = 5,
    prompt           = "INITIALIZE MU/TH/UR ? (Y/N) : ",
)


# ---------------------------------------------------------------------------
# Campagne
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="/dev/ttyUSB0")
    parser.add_argument("--baud",   type=int, default=4800)
    parser.add_argument("--reset",  action="store_true")
    args = parser.parse_args()

    save = "nostromo_save.json"
    if args.reset and os.path.isfile(save):
        os.remove(save)

    campaign = Campaign(
        device    = args.device,
        baud      = args.baud,
        save_file = save,
    )
    campaign.boot = boot
    campaign.menu = main_menu
    campaign.run()


if __name__ == "__main__":
    main()
