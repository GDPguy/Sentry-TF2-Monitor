# Sentry — TF2 Server Monitor

Sentry is a tool for Team Fortress 2 to monitor in-game players in your current server. It flags suspected cheaters using TF2 Bot Detector/user lists, optionally fetches ban histories of connected players, and automates commands.

## Features

- **Cheater detection / tagging**
  - Uses TF2 Bot Detector lists and your own user list.
  - Mark players as **Cheater / Suspicious / Other**.
- **Notes**
  - Attach custom notes to players
  - Notes show up alongside the player in the UI
- **Automation (off by default)**
  - Announce connected cheaters to global chat
  - Automatically callvote-kick detected cheaters
  - Party chat announcements:
    - New cheaters detected
    - Suspicious SourceBans keyword matches (e.g. "aimbot")
- **User list management**
  - Edit entries and notes from the GUI.
  - Export your list in TF2BD format from the User List Manager for sharing

## Download (Recommended)
Most users should **download the latest precompiled release**.

1. Go to the **Releases** page and download the newest build for your OS.
2. Extract it, and run the Sentry executable for your system.

If the precompiled build doesn’t work on your system, you can run from source instead (see below).

## TF2 Launch Options (Required)
Add the following to your TF2 launch options in Steam:

- `-usercon -g15 +ip 0.0.0.0 +rcon_password password +net_start`

Optional:
- `-port 27015` (only if another application is already using the default port; set it to whatever you want)

Then set the same **RCON password**/**port** inside Sentry via **Settings**.

## Configuration
All settings (RCON password/port, SteamHistory API key, list options, automation, UI scale, etc.) are configurable from the **Settings** button in the GUI.
Settings are saved to:

- `cfg/settings.ini`

Get a SteamHistory API key (optional):
- https://steamhistory.net/api

## Run From Source 
Only use this if you don’t want the precompiled release.

### Prerequisites (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3-tk python3-venv python3-pip
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
Double-click start_sentry.bat
## Build with PyInstaller 
The precompiled builds in **Releases** are built using Python 3.13.7, for reproducibility (and with pinned dependencies). 
#### Linux
Use the provided script `compile.sh`
#### Windows
Use `compile.bat`
## Notes / Troubleshooting
- If Sentry says RCON is unreachable:
  - Verify TF2 is running with the launch options above.
  - Verify your **RCON password** matches in both TF2 and Sentry.
  - Verify your **RCON port** matches (default `27015`).
  - If the port is in use by another app, change it in Sentry and add `-port <newport>` to TF2 launch options.
