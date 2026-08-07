import os
import psutil
import re
from .models import PlayerInstance
from .utils import convert_steamid64_to_steamid3

class TF2Monitor:
    @staticmethod
    def is_process_running():
        tf2_exes = {'tf_win64.exe', 'tf.exe', 'tf_linux64'}
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in tf2_exes:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return False

    @staticmethod
    def detect_steamid_from_process():
        # Prefer Steam.exe over steamwebhelper.exe. Since the 2023 Steam CEF
        # rewrite, steamwebhelper.exe lives at <install>/bin/cef/cef.win64/ on
        # Windows (and the process_iter order isn't guaranteed), so picking the
        # first match almost always grabs a deep path whose parent dir has no
        # config/loginusers.vdf. Steam.exe always sits directly in the install
        # root next to config/.
        steam_exe = None
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                name = (proc.info.get('name') or '').lower()
                exe = proc.info.get('exe')
                # Strip ".exe" because psutil on Windows returns names with
                # the extension (steam.exe) but on Linux/Mac returns bare names
                # (steam). The original code's "name in {steam, steamwebhelper}"
                # check never matched anything on a default Windows psutil.
                if name.endswith('.exe'):
                    name = name[:-4]
                if name == 'steam' and exe:
                    steam_exe = os.path.abspath(exe)
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not steam_exe:
            return None

        # Walk up the directory tree to find config/loginusers.vdf.
        # - Windows: <install>/Steam.exe  -> config/ is alongside it
        # - Steam Play / Proton: <install>/ubuntu12_32/steam -> config/ is one level up
        search = os.path.dirname(steam_exe)
        config_path = None
        for _ in range(4):
            if not search or search == os.path.dirname(search):
                break
            candidate = os.path.join(search, 'config', 'loginusers.vdf')
            if os.path.exists(candidate):
                config_path = candidate
                break
            search = os.path.dirname(search)

        if not config_path:
            return None

        users = {}
        current_id = None
        kv_re = re.compile(r'^\s*"([^"]+)"\s*"([^"]*)"\s*$')
        id_re = re.compile(r'^\s*"(\d{17,})"\s*$')

        try:
            with open(config_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    m_id = id_re.match(line)
                    if m_id:
                        current_id = m_id.group(1)
                        users[current_id] = {}
                        continue

                    if line == "}":
                        current_id = None
                        continue

                    m_kv = kv_re.match(line)
                    if m_kv and current_id:
                        k, v = m_kv.groups()
                        users[current_id][k] = v
        except Exception as e:
            print(f"Error parsing loginusers.vdf: {e}")
            return None

        found_sid64 = None
        for sid, info in users.items():
            if info.get("MostRecent", "0") == "1":
                found_sid64 = sid
                break

        # Fallback: pick the user with the most recent Timestamp. Some Steam
        # installs never write the "MostRecent" field (esp. when the user was
        # last logged in via a launcher shortcut rather than the Steam client),
        # so without this fallback detection always returns None.
        if not found_sid64:
            best_ts = -1
            for sid, info in users.items():
                try:
                    ts = int(info.get("Timestamp", "0"))
                except (TypeError, ValueError):
                    ts = 0
                if ts > best_ts:
                    best_ts = ts
                    found_sid64 = sid

        if found_sid64:
            return convert_steamid64_to_steamid3(found_sid64)

        return None

    @staticmethod
    def parse_g15_dump(response):
        if not response.strip(): return False, [], [], [], [], None

        pattern_connected = re.compile(r'm_bConnected\[(\d+)\] bool \((true|false)\)')
        pattern_name = re.compile(r'm_szName\[(\d+)\] string \((.*)\)')
        pattern_ping = re.compile(r'm_iPing\[(\d+)\] integer \((\d+)\)')
        pattern_score = re.compile(r'm_iScore\[(\d+)\] integer \((\d+)\)')
        pattern_deaths = re.compile(r'm_iDeaths\[(\d+)\] integer \((\d+)\)')
        pattern_team = re.compile(r'm_iTeam\[(\d+)\] integer \((\d+)\)')
        pattern_account_id = re.compile(r'm_iAccountID\[(\d+)\] integer \((\d+)\)')
        pattern_user_id = re.compile(r'm_iUserID\[(\d+)\] integer \((\d+)\)')
        pattern_user_team = re.compile(r'm_iTeamNum integer \((\d+)\)')

        connected_data = dict(pattern_connected.findall(response))
        name_data = dict(pattern_name.findall(response))
        ping_data = dict(pattern_ping.findall(response))
        score_data = dict(pattern_score.findall(response))
        deaths_data = dict(pattern_deaths.findall(response))
        team_data = dict(pattern_team.findall(response))
        userid_data = dict(pattern_user_id.findall(response))
        account_data = dict(pattern_account_id.findall(response))

        local_team_val = None
        userteamraw = pattern_user_team.search(response)
        if userteamraw:
            try:
                team_number_int = int(userteamraw.group(1))
                if team_number_int == 3: local_team_val = "Blue"
                elif team_number_int == 2: local_team_val = "Red"
                elif team_number_int == 1: local_team_val = "Spectator"
                elif team_number_int == 0: local_team_val = "Unassigned"
            except ValueError:
                pass
        else:
            print("Parsing G15 failed: local team missing")
            return False, [], [], [], [], None

        # Completeness check
        expected_indices = set(str(i) for i in range(102))

        if not (
            set(connected_data.keys()) == expected_indices and
            set(name_data.keys()) == expected_indices and
            set(ping_data.keys()) == expected_indices and
            set(score_data.keys()) == expected_indices and
            set(deaths_data.keys()) == expected_indices and
            set(team_data.keys()) == expected_indices and
            set(userid_data.keys()) == expected_indices and
            set(account_data.keys()) == expected_indices
        ):
            print("Parsing G15 failed: indices mismatch")
            return False, [], [], [], [], None

        # Strict name validation
        for idx_str in expected_indices:
            if connected_data[idx_str] == 'true':
                if not name_data[idx_str]:
                    print("Parsing G15 failed: idx_str not in indices")
                    return False, [], [], [], [], None

        parsed_red = []
        parsed_blue = []
        parsed_spectator = []
        parsed_unassigned = []

        # Player Object Creation
        for idx_str in expected_indices:
            is_connected = connected_data[idx_str]
            if is_connected == 'false': continue

            # Bot filter: Ping == 0, alternative heuristic might be to filter steamids < 1k, or if servers can give bots fake ping (can...do they?), both
            try: ping_val = int(ping_data.get(idx_str, "0"))
            except ValueError: ping_val = 0
            if ping_val == 0: continue

            name = name_data[idx_str]
            try: raw_account_id = int(account_data[idx_str])
            except ValueError: continue
            if raw_account_id == 0: continue

            steamid = f"[U:1:{raw_account_id}]"
            userid = userid_data[idx_str]
            if int(userid) == 0: continue

            kills = score_data.get(idx_str, "0")
            deaths = deaths_data.get(idx_str, "0")

            try: raw_team = int(team_data[idx_str])
            except ValueError: continue

            team_str = "Unknown"
            if raw_team == 2: team_str = "Red"
            elif raw_team == 3: team_str = "Blue"
            elif raw_team == 1: team_str = "Spectator"
            elif raw_team == 0: team_str = "Unassigned"
            else: continue

            player = PlayerInstance(
                userid, name, ping_val, steamid, kills, deaths,
                player_type=None, team=team_str
            )

            if team_str == "Red": parsed_red.append(player)
            elif team_str == "Blue": parsed_blue.append(player)
            elif team_str == "Spectator": parsed_spectator.append(player)
            elif team_str == "Unassigned": parsed_unassigned.append(player)

        return True, parsed_red, parsed_blue, parsed_spectator, parsed_unassigned, local_team_val
