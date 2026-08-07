APP_VERSION = "1.2.0"

# Built-in TF2BD community player lists shipped with the app. Each entry is
# (display_name, url, filename) where `filename` is what the JSON will be
# saved as locally under tf2bd_lists/ and what the in-app list manager
# keys on. The URL is what we fetch from; once a file is saved, its own
# file_info.update_url becomes the source of truth for subsequent
# auto-updates.
#
# These were verified to be reachable and use the v3 TF2BD schema. The
# official PazerOP list isn't hosted publicly (it ships inside the TF2BD
# binary, and that repo was archived March 2024), so we fall back to
# community-maintained lists.
BUILTIN_TF2BD_LISTS = [
    (
        "Cleffy's TF2BD List",
        'https://raw.githubusercontent.com/Cl3ffy/cleffy-list/main/playerlist.cleffy.json',
        'playerlist.cleffy.json',
    ),
    (
        "joekiller's TF2BD List",
        'https://raw.githubusercontent.com/joekiller/joekiller-list/main/playerlist.joekiller.json',
        'playerlist.joekiller.json',
    ),
    (
        "qfoxb's TF2BD List",
        'https://raw.githubusercontent.com/qfoxb/tf2bd-lists/main/playerlist.qfoxb.json',
        'playerlist.qfoxb.json',
    ),
    (
        "Classic's TF2BD List (US East)",
        'https://raw.githubusercontent.com/Classic-Gaming/tf2db/main/playerlist.classic.json',
        'playerlist.classic.json',
    ),
    (
        "TF2 Bot Detector ASEAN List",
        'https://raw.githubusercontent.com/Critical-Cookie/TF2BD-ASEAN-LIST/main/playerlist.asean.json',
        'playerlist.asean.json',
    ),
]

DEFAULT_SETTINGS = {
    'User': '[U:1:XXXXXXXXXX]',
    'Use_Manual_SteamID': 'False',
    'RCon_Password': 'yourpassword',
    'RCon_Port': '27015',
    'Steam_API_Key': '',
    'SteamHistory_API_Key': '',
    'Auto_Update_TF2BD_Lists': 'False',
    'Kick_Cheaters': 'False',
    'Announce_Cheaters': 'False',
    'Announce_Cheaters_Interval': '15',
    'Party_Announce_Cheaters': 'False',
    'Party_Announce_Bans': 'False',
    'UI_Scale': '1.0',
    'Color_Self': '#44cc44',       # Green
    'Color_Cheater': '#ff4444',    # Red
    'Color_Suspicious': '#e6b800', # Yellow
    'Color_Other': '#888888',      # Gray
    'Save_Player_Names': 'True',
    'Save_Player_Timestamps': 'True',
    'Show_SteamID_Column': 'False',
    'Show_Ping_Column': 'True',
    'Show_Kills_Column': 'True',
    'Show_Deaths_Column': 'True',
    'Show_Age_Column': 'True',
    'Show_Hours_Column': 'True',
    'Show_VAC_Column': 'False',
    'Show_GameBans_Column': 'False',
    'Show_SB_Column': 'True'
}
