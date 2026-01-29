# Sentry — TF2 Server Monitor

Sentry is a cross-platform tool for Team Fortress 2 to monitor in-game players in your current server. It flags cheaters using TF2 Bot Detector/user lists, fetches ban histories of connected players (also keyword matches bans for cheating), and automates commands. It is an alternative to (now unmaintained) [TF2 Bot Detector](https://github.com/PazerOP/tf2_bot_detector) and is compatible with its player lists.

<img width="541" height="554.5" alt="art" src="https://github.com/user-attachments/assets/29861291-c5a3-45c8-bb74-3122639b32cc" />


<sub>matches system theme, will look different on different platforms/light mode</sub>

## Features
- **Cheater detection / tagging**
  - Uses TF2 Bot Detector player lists and your own user list.
  - Mark players as **Cheater / Suspicious / Other** by right-clicking.
  - Attach notes to a player by double-clicking the 'notes' section of a player to quick edit, or use the context menu
- **Automation (off by default)**
  - Announce connected cheaters to global chat
  - Automatically callvote-kick detected cheaters
  - Party chat announcements:
    - Notifies party chat when new cheaters are detected/present in a server
    - Notifies party chat when players with suspicious SourceBans are detected (keyword matches (e.g. "aimbot")
      - Players with suspicious SourceBans are indicated in the GUI with bold red text. Double-click or use the context menu to view them
- **User list management**
  - Edit entries and notes from the GUI.
  - Export your list in TF2BD format from the User List Manager for sharing
- **Social Graph**
  - See who is friends with who
  - **Player relationships:** If Player A is friends with B, and B is friends with C, they are all identified as a single linked group. This feature is intended for Casual Mode to identify potential party stacks.
  - **Tooltips:** Hover over the cell in the `#` column to see exactly how a group is connected. It distinguishes between **Direct Friends** (Steam friends) and **Indirectly Linked** players (friends of friends).
## Download (Recommended)
Most users should **download the latest precompiled release**.

1. Go to [releases](https://github.com/GDPguy/Sentry-TF2/releases) and download the latest build for your OS.
2. Extract to a folder
- On Linux, you may need to run `chmod +x Sentry` in the terminal.

When running the executable, /cfg/ and /tf2bd/ folders are created automatically.

If the precompiled build doesn’t work on your system, you can run from source instead (see below).

## TF2 Launch Options (Required)
Add the following to your TF2 launch options in Steam:

- `-usercon -g15 +ip 0.0.0.0 +rcon_password yourpassword +net_start`

Optional:
- ` +sv_rcon_whitelist_address 127.0.0.1` (prevents being banned by rcon on too many failed attempts)
- `-port 27015` (only if another application is already using the default port; set it to whatever you want)

Then set the same **RCON password**/**port** inside Sentry via **Settings**.

The default password 'yourpassword' should be fine. You do not necessarily need to change it.

## Configuration
All settings are configurable from the **Settings** button in the GUI.
Settings are saved to:

- `cfg/settings.ini`
Get a Steam Web API key (optional, **Recommended**):
Go to https://steamcommunity.com/dev/apikey log in and set the domain name to whatever, like localhost. Click register, then copy your api key into settings.
- Required for **Social Graph/Friend detection** and fetching avatars/account age/playtime
Get a SteamHistory API key (optional, **Recommended**):
Go to https://steamhistory.net/api and sign in with your steam account, you should be able to get one from there.
- Required for **SourceBans** integration.

## Player Lists
Sentry uses player lists originally created for [TF2 Bot Detector](https://github.com/PazerOP/tf2_bot_detector)

Place TF2BD player lists in the ./tf2bd/ folder. 
- **Importing:** Place TF2BD player lists into the `./tf2bd/` folder.
- **Exporting:** Use the **User List Manager** to export your userlist into a TF2BD-compatible JSON file to share with others. 

Note: Only Cheater & Suspicious player types will be exported at this time. This software only uses the 'Cheater' and 'Suspicious' attributes from TF2BD lists; exporting players marked 'Other'
does not cleanly match those attributes. 

## Run From Source 
Only use this if you don’t want the precompiled release. This assumes you have Python 3.13 installed, newer versions haven't been tested but probably work just fine.

### Prerequisites (Ubuntu)
Ubuntu doesn't ship with these preinstalled, so you will have to install them:
```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

### Setup
#### Linux
In terminal, make start_sentry.sh executable:
`chmod +x start_sentry.sh`

Then:
`./start_sentry.sh`

or from terminal:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

#### Windows
Double-click `start_sentry.bat`
## Build with PyInstaller
#### Linux
Use the provided script `compile.sh`
#### Windows
Use `compile.bat`
## Notes / Troubleshooting
- If Sentry says RCON is unreachable:
  - Verify TF2 is running with the launch options above.
  - Verify your **RCON password** matches in both your TF2 launch options and Sentry.
  - Verify your **RCON port** matches (default `27015`) in both your TF2 launch options and Sentry.
