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
        steam_exe = None
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                name = (proc.info.get('name') or '').lower()
                exe = proc.info.get('exe')
                if name.endswith('.exe'):
                    name = name[:-4]
                if name == 'steam' and exe:
                    steam_exe = os.path.abspath(exe)
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not steam_exe:
            return None

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

        # Legacy 
        for sid, info in users.items():
            if info.get("MostRecent", "0") == "1":
                found_sid64 = sid
                break

        # current behavior: prio latest timestamp
        # falls back on first entry if all timestamps are invalid
        # might consider a best_ts value of 0 instead to ensure no false positives
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
    def parse_dumpstringtables(response):
        mapdata = {}
        if not response:
            return None
        
        pattern_map = re.compile(r'maps\\(.*)\.bsp')

        match = pattern_map.search(response)
        map_name = match.group(1).strip() if match else None
        mapdata["name"] = map_name

        #Parsing map names to find contract folder
        contract_folders = {
            "official maps": [
                "koth_harvest_event",
                "plr_hightower_event",
                "sd_doomsday_event",
                "cp_manor_event",
                "koth_viaduct_event",
                "koth_lakeside_event"
            ],
            "community maps 1": [
                "pl_fifthcurve_event",
                "koth_bagel_event",
                "pd_cursed_cove_event",
                "cp_gorge_event",
                "pl_rumble_event",
                "pl_millstone_event",
                "koth_slaughter_event",
                "koth_maple_ridge_event",
                "pd_monster_bash",
                "koth_moonshine_event",
                "pl_precipice_event_final",
                "cp_sunshine_event",
                "koth_slasher",
                "pd_pit_of_death_event"
            ],
            "community maps 2": [
                "pd_farmageddon",
                "arena_lumberyard_event",
                "pl_hasslecastle",
                "koth_los_muertos",
                "koth_megalo",
                "koth_undergrove_event",
                "koth_synthetic_event",
                "pl_terror_event",
                "pl_bloodwater",
                "cp_ambush_event"
            ],
            "community maps 3": [
                "ctf_crasher",
                "plr_hacksaw_event",
                "koth_sawmill_event",
                "cp_spookeyridge",
                "pl_sludgepit_event",
                "ctf_helltrain_event"
            ],
            "community maps 4": [
                "pl_spineyard",
                "cp_lavapit_final",
                "pd_mannsylvania",
                "koth_slime",
                "arena_perks",
                "pl_corruption",
                "cp_degrootkeep_rats",
                "zi_murky",
                "zi_atoll",
                "zi_woods",
                "zi_sanitarium",
                "zi_devastation_final1"
            ],
            "community maps 5": [
                "koth_toxic",
                "cp_darkmarsh",
                "cp_freaky_fair",
                "tow_dynamite",
                "pd_circus",
                "vsh_outburst",
                "zi_blazehattan",
                "cp_cowerhouse",
                "koth_dusker",
                "ctf_doublecross_event",
                "arena_afterlife",
                "htf_marshlands"
            ],
            "community maps 6": [
                "cp_holyhell",
                "cp_wildcat_event",
                "pl_aridpass_event",
                "koth_trainsawlaser",
                "ctf_medi_evil"
            ]
        }
        
        mapdata["contract_page"] = next(
            (folder for folder, maps in contract_folders.items() if map_name in maps),
            None
        )
        
        return mapdata #lets return everything needed for print, which is map name and contract folder. It'll be more efficient.

    @staticmethod
    def parse_net_channels(response):
        if response.strip() == "No active net channels." or not response.strip():
            return None
        else:
            pattern_remote_ip = re.compile(r'remote IP: (loopback|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}\b)\s')
            ip = pattern_remote_ip.search(response)
            if ip:
                return ip.group(1)
            return None
        
    @staticmethod
    def parse_TPD(response):
        if not response or response.strip() == "Failed to find party shared object":
            return None
            
        pattern_queues = re.compile(r'In (\d) queues:')
        pattern_leader_id = re.compile(r'LeaderID: (\[U:\d:\d*\])')  #leader_id: (\d*) captures the leader's id64 in the body of response, sometimes we get no body though...
        pattern_member_ids = re.compile(r'member_ids:\s*([\d,\s]+)\s') #REVIEW
        
        sQueues = pattern_queues.search(response)
        sLeader_id = pattern_leader_id.search(response)
        member_id64s = pattern_member_ids.findall(response)
        
        if not sQueues:
            queue_count = 0
        else:
            queue_count = int(sQueues.group(1))
            
        if not sLeader_id:
            leader_id = None
        else:
            leader_id = str(sLeader_id.group(1))
        
        member_ids = []
        if member_id64s:
            for id64 in member_id64s:
                member_ids.append(convert_steamid64_to_steamid3(id64))
        
        return {"leader_id": leader_id, "member_ids": member_ids, "in_queue": queue_count} 

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
