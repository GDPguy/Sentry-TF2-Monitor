import threading
import time
import requests
import datetime
from collections import deque
from .config import ConfigManager
from .rcon import RConManager
from .list_manager import ListManager
from .tf2_monitor import TF2Monitor
from .utils import convert_steamid3_to_steamid64
import re
import concurrent.futures

class AppLogic:
    def __init__(self):
        self.state_lock = threading.RLock()

        self.cfg = ConfigManager()
        self.rcon = RConManager(self.cfg)
        self.lists = ListManager(self.cfg, self.state_lock)

        self.connected_red_players = []
        self.connected_blue_players = []
        self.connected_spectator_players = []
        self.connected_unassigned_players = []
        self.user_current_team = None
        self.recently_played = []

        self.chat_queue = deque()
        self._chat_pending = set()
        self._chat_recent = {}
        self.last_chat_time = 0.0
        self.chat_delay = 1.0
        self._chat_recent_ttl = 5.0

        self.session_seen_players = set()
        self.announced_party_cheaters = set()
        self.announced_party_bans = set()
        self.suspicious_steamids = set()
        self.cached_detected_steamid = None

        self.last_kick_time = 0.0
        self.last_announce_time = 0.0
        self.automation_lock = threading.Lock()
        self._automation_stop = threading.Event()
        self._automation_thread = None
        self._last_good_g15 = 0.0

        self._kick_lock = threading.Lock()
        self.tf2_running = False

        self.steamhistory_lock = threading.Lock()
        self.steamhistory_bans = {}
        self.steamhistory_cache = {}

        self.steam_api_lock = threading.Lock()
        self.steam_api_cache = {}
        self.api_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

        boundary_roots = ["cheat", "hack", "aimbot", "wallhack"]
        self.ban_pattern = re.compile(r"\b(" + "|".join(boundary_roots) + r")", re.IGNORECASE)
        self.ban_tags = ["[stac]", "smac ", "[ac]", "anti-cheat"]

        self.lists.load_all()
        self.auto_detect_steamid()

    def get_setting(self, k): return self.cfg.get(k)
    def get_setting_bool(self, k): return self.cfg.get_bool(k)
    def get_setting_float(self, k): return self.cfg.get_float(k)
    def get_setting_int(self, k): return self.cfg.get_int(k)
    def get_setting_color(self, k): return self.cfg.get_color(k)

    def set_setting(self, k, v):
        current = self.cfg.get(k)
        new_val = str(v)
        if current != new_val:
            self.cfg.set(k, new_val)
            if k in ('RCon_Password', 'RCon_Port'):
                self.rcon.reset()

    def auto_detect_steamid(self):
        sid = TF2Monitor.detect_steamid_from_process()
        if sid: self.cached_detected_steamid = sid

    def get_current_user_steamid3(self):
        if self.get_setting_bool('Use_Manual_SteamID'):
            return self.get_setting('User')

        if not self.cached_detected_steamid:
            self.auto_detect_steamid()

        return self.cached_detected_steamid or self.get_setting('User')

    def get_recently_played_snapshot(self):
        with self.state_lock:
            return list(self.recently_played)

    def update_steam_api_data(self, steamids):
        api_key = self.get_setting("Steam_API_Key")
        if not api_key or len(api_key) < 10: return

        now = time.monotonic()
        to_query_summary = []
        to_query_bans = []
        to_query_playtime = []

        with self.steam_api_lock:
            for sid in steamids:
                entry = self.steam_api_cache.get(sid, {})
                last = entry.get('last_update', 0)

                if (now - last) > 1800:
                    to_query_summary.append(sid)
                    to_query_bans.append(sid)

                if 'playtime' not in entry:
                    to_query_playtime.append(sid)

        def get_map(sids):
            m = {}
            for s in sids:
                s64 = convert_steamid3_to_steamid64(s)
                if s64: m[str(s64)] = s
            return m

        if to_query_summary or to_query_bans:
            threading.Thread(target=self._worker_batch_api,
                             args=(api_key, get_map(to_query_summary), get_map(to_query_bans)),
                             daemon=True).start()

        sid_map_play = get_map(to_query_playtime[:32])
        for s64, sid3 in sid_map_play.items():
            with self.steam_api_lock:
                if 'playtime' not in self.steam_api_cache.setdefault(sid3, {}):
                    self.steam_api_cache[sid3]['playtime'] = None # Placeholder

            self.api_executor.submit(self._worker_single_playtime, api_key, s64, sid3)

    def _worker_batch_api(self, key, map_summ, map_bans):
        if map_summ:
            try:
                ids = list(map_summ.keys())
                for i in range(0, len(ids), 100):
                    chunk = ids[i:i+100]
                    r = requests.get("http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
                                     params={'key': key, 'steamids': ",".join(chunk)}, timeout=5)
                    for p in r.json().get('response', {}).get('players', []):
                        sid3 = map_summ.get(p['steamid'])
                        if sid3:
                            with self.steam_api_lock:
                                e = self.steam_api_cache.setdefault(sid3, {})
                                e['avatar'] = p.get('avatar')
                                e['last_update'] = time.monotonic()
            except Exception: pass

        if map_bans:
            try:
                ids = list(map_bans.keys())
                for i in range(0, len(ids), 100):
                    chunk = ids[i:i+100]
                    r = requests.get("http://api.steampowered.com/ISteamUser/GetPlayerBans/v1/",
                                     params={'key': key, 'steamids': ",".join(chunk)}, timeout=5)
                    for b in r.json().get('players', []):
                        sid3 = map_bans.get(b['SteamId'])
                        if sid3:
                            with self.steam_api_lock:
                                e = self.steam_api_cache.setdefault(sid3, {})
                                e['vac'] = b.get('VACBanned', False)
                                e['game_bans'] = b.get('NumberOfGameBans', 0)
            except Exception: pass

    def _worker_single_playtime(self, key, s64, sid3):
        try:
            r = requests.get("http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/",
                             params={'key': key, 'steamid': s64, 'format': 'json',
                                     'include_played_free_games': 1, 'appids_filter[0]': 440}, timeout=5)

            data = r.json().get('response', {})
            val = None

            if 'games' in data:
                games = data.get('games', [])
                tf2 = next((g for g in games if g['appid'] == 440), None)

                if tf2:
                    minutes = tf2.get('playtime_forever', 0)
                    if minutes > 0:
                        val = minutes
                    else:
                        val = None # if they are in game, their minutes are likely not 0, so we assume game details/total playtime was set to private

            with self.steam_api_lock:
                self.steam_api_cache.setdefault(sid3, {})['playtime'] = val

        except Exception:
            with self.steam_api_lock:
                 if sid3 in self.steam_api_cache:
                     self.steam_api_cache[sid3].pop('playtime', None)


    def get_players(self):
        running = TF2Monitor.is_process_running()
        with self.state_lock:
            self.tf2_running = running
        if not running:
            self._reset_state()
            self.rcon.reset()
            return 'tf2_closed', [], [], []

        self._process_chat_queue()

        t0 = time.monotonic()
        ok, response = self.rcon.execute("g15_dumpplayer")
        dt = time.monotonic() - t0
        if dt > 1.5:
            print(f"g15_dumpplayer took {dt:.2f}s")

        if response == "__TIMEOUT__":
            with self.state_lock:
                cached_red = list(self.connected_red_players)
                cached_blue = list(self.connected_blue_players)
                cached_spec = list(self.connected_spectator_players)
                cached_unassigned = list(self.connected_unassigned_players)
            return 'lobby_found', cached_red, cached_blue, cached_spec + cached_unassigned

        if self.rcon.block_reason:
            return self.rcon.block_reason, [], [], []

        if not ok:
            self._reset_state()
            return 'connection_failed', [], [], []

        if not response.strip():
            self._reset_state()
            return 'lobby_not_found', [], [], []

        success, red, blue, spec, unassigned, local_team = TF2Monitor.parse_g15_dump(response)

        if not success:
            with self.state_lock:
                cached_red = list(self.connected_red_players)
                cached_blue = list(self.connected_blue_players)
                cached_spec = list(self.connected_spectator_players)
                cached_unassigned = list(self.connected_unassigned_players)
            return 'lobby_found', cached_red, cached_blue, cached_spec + cached_unassigned

        all_players = red + blue + spec + unassigned
        all_sids = [p.steamid for p in all_players]
        self.update_steam_api_data(all_sids)

        for p in all_players:
            p.player_type = self.lists.identify_player_type(p.steamid)
            p.notes = self.lists.get_user_notes(p.steamid)
            p.mark_label = self.lists.get_mark_label(p.steamid)
            p.ban_count = self.get_sourcebans_count(p.steamid)

            api_data = self.steam_api_cache.get(p.steamid, {})
            p.avatar_url = api_data.get('avatar')
            p.vac_banned = api_data.get('vac', False)
            p.game_bans = api_data.get('game_bans', 0)
            p.tf2_playtime = api_data.get('playtime')

        with self.state_lock:
            self.user_current_team = local_team
            self.connected_red_players = red
            self.connected_blue_players = blue
            self.connected_spectator_players = spec
            self.connected_unassigned_players = unassigned

            for p in all_players:
                self._update_last_seen(p)

            self.lists.update_recently_played(all_players, self.recently_played)

            current_ids = set(all_sids)
            self.announced_party_cheaters &= current_ids
            self.announced_party_bans &= current_ids
            self.suspicious_steamids &= current_ids

            self._last_good_g15 = time.monotonic()

            pdata = ('lobby_found', list(red), list(blue), list(spec + unassigned))

        self.update_sourcebans(all_sids)
        self.analyze_suspicious_sourcebans(all_players)
        self.check_party_announcements(all_players)

        return pdata

    def _reset_state(self):
        with self.state_lock:
            self.user_current_team = None
            self.connected_red_players = []
            self.connected_blue_players = []
            self.connected_spectator_players = []
            self.connected_unassigned_players = []
            self.session_seen_players.clear()
            self.announced_party_cheaters.clear()
            self.announced_party_bans.clear()
            self.suspicious_steamids.clear()

    def _update_last_seen(self, player):
        if player.steamid not in self.session_seen_players:
            if self.lists.is_in_userlist(player.steamid):
                self.lists.touch_user_entry(player.steamid, player.name)
                self.session_seen_players.add(player.steamid)

    def queue_chat(self, msg, chat_type):
        valid_chat_types = {'say', 'tf_party_chat', 'say_team'}
        if chat_type not in valid_chat_types: return

        CHUNK_SIZE = 120
        chunks = [msg[i:i + CHUNK_SIZE] for i in range(0, len(msg), CHUNK_SIZE)]

        with self.state_lock:
            for chunk in chunks:
                key = (chat_type, chunk)
                if key in self._chat_pending: continue
                self._chat_pending.add(key)
                self.chat_queue.append(key)

    def _process_chat_queue(self):
        with self.state_lock:
            if not self.chat_queue: return

            now = time.monotonic()
            if (now - self.last_chat_time) < self.chat_delay: return

            if self.user_current_team not in ("Red", "Blue", "Spectator"):
                return

            key = self.chat_queue[0]
            chat_type, message = key

            last_sent = self._chat_recent.get(key, 0.0)
            if last_sent and (now - last_sent) < self._chat_recent_ttl:
                self.chat_queue.popleft()
                self._chat_pending.discard(key)
                return

        ok, _ = self.rcon.execute(f'{chat_type} "{message}"')

        with self.state_lock:
            if ok:
                now = time.monotonic()
                self.chat_queue.popleft()
                self._chat_pending.discard(key)
                self.last_chat_time = now
                self._chat_recent[key] = now
                if len(self._chat_recent) > 500:
                    self._chat_recent.clear()

    def start_automation_thread(self):
        if self._automation_thread and self._automation_thread.is_alive():
            return
        self._automation_stop.clear()

        def _loop():
            while not self._automation_stop.is_set():
                self.run_automation_bg()
                time.sleep(1.0)

        self._automation_thread = threading.Thread(target=_loop, daemon=True)
        self._automation_thread.start()

    def stop_automation_thread(self):
        self._automation_stop.set()

    def kick_player(self, steamid):
        target_uid = None
        with self.state_lock:
            all_p = self.connected_red_players + self.connected_blue_players + self.connected_spectator_players + self.connected_unassigned_players
            for p in all_p:
                if p.steamid == steamid:
                    target_uid = p.userid
                    break

        if target_uid:
            def worker():
                if not self._kick_lock.acquire(blocking=False):
                    return
                try:
                    self.rcon.execute(f"callvote kick {target_uid}")
                finally:
                    self._kick_lock.release()

            threading.Thread(target=worker, daemon=True).start()
            return True
        return False

    def run_automation_bg(self):
        if time.monotonic() - self._last_good_g15 > 5.0:
            return
        with self.state_lock:
            if not getattr(self, "tf2_running", False):
                return

        if not self.automation_lock.acquire(blocking=False):
            return
        try:
            self._loop_kick_cheaters()
            self._loop_announce_cheaters()
        finally:
            self.automation_lock.release()

    def _loop_kick_cheaters(self):
        if not self.get_setting_bool('Kick_Cheaters'): return

        interval = self.get_setting_int('Kick_Cheaters_Interval')

        now = time.monotonic()
        if (now - self.last_kick_time) < interval:
            return

        with self.state_lock:
            if self.user_current_team == "Red":
                target_list = list(self.connected_red_players)
            elif self.user_current_team == "Blue":
                target_list = list(self.connected_blue_players)
            else:
                return

        kicked = False
        for p in target_list:
            if self.lists.identify_player_type(p.steamid) == "Cheater":
                self.rcon.execute(f"callvote kick {p.userid}")
                print(f"attempting to call a votekick on {p.name}")
                kicked = True
                break

        if kicked:
            self.last_kick_time = now

    def _loop_announce_cheaters(self):
        if not self.get_setting_bool('Announce_Cheaters'): return
        interval = self.get_setting_int('Announce_Cheaters_Interval')

        now = time.monotonic()
        if (now - self.last_announce_time) < interval:
            return

        cheaters = []
        all_p = None
        with self.state_lock:
            all_p = list(self.connected_red_players) + list(self.connected_blue_players) + \
                    list(self.connected_spectator_players) + list(self.connected_unassigned_players)

        cheaters = [p.name for p in all_p if self.lists.identify_player_type(p.steamid) == "Cheater"]

        if cheaters:
            msg = f"[Sentry] Found {len(cheaters)} cheater(s): {', '.join(cheaters)}"
            self.queue_chat(msg, "say")
            self.last_announce_time = now

    def analyze_suspicious_sourcebans(self, all_players):
        with self.state_lock:
            for p in all_players:
                if p.steamid in self.suspicious_steamids:
                    continue

                with self.steamhistory_lock:
                    bans = self.steamhistory_bans.get(p.steamid, [])

                found_match = False
                for ban in bans:
                    if ban.get('CurrentState') == 'Unbanned':
                        continue

                    reason = ban.get('BanReason', '').lower()
                    if self.ban_pattern.search(reason):
                        found_match = True
                    elif not found_match:
                        if any(t in reason for t in self.ban_tags):
                            found_match = True

                    if found_match:
                        break

                if found_match:
                    self.suspicious_steamids.add(p.steamid)

    def check_party_announcements(self, all_players):
        if self.get_setting_bool("Party_Announce_Cheaters"):
            new_cheaters = []
            with self.state_lock:
                for p in all_players:
                    if p.steamid in self.announced_party_cheaters: continue
                    if self.lists.identify_player_type(p.steamid) == "Cheater":
                        new_cheaters.append(p.name)
                        self.announced_party_cheaters.add(p.steamid)

            if new_cheaters:
                self.queue_chat(f"[Sentry] Cheaters found: {', '.join(new_cheaters)}", "tf_party_chat")

        if self.get_setting_bool("Party_Announce_Bans"):
            new_sus = []
            with self.state_lock:
                for p in all_players:
                    if p.steamid in self.suspicious_steamids and p.steamid not in self.announced_party_bans:
                        new_sus.append(p.name)
                        self.announced_party_bans.add(p.steamid)

            if new_sus:
                self.queue_chat(f"[Sentry] Possible cheaters (Sourceban keyword match): {', '.join(new_sus)}", "tf_party_chat")

    def update_sourcebans(self, steamids):
        if not self.get_setting_bool("Enable_Sourcebans_Lookup"): return
        key = self.get_setting("SteamHistory_API_Key")
        if not key: return

        now = datetime.datetime.now().timestamp()
        to_query = []

        with self.steamhistory_lock:
            for sid in steamids:
                last_check = self.steamhistory_cache.get(sid, 0)
                if (now - last_check) > 86400:
                    to_query.append(sid)
                    self.steamhistory_cache[sid] = now

        if not to_query: return

        def worker():
            s64_list = []
            for s in to_query:
                conv = convert_steamid3_to_steamid64(s)
                if conv: s64_list.append(str(conv))

            if not s64_list: return

            chunk_size = 100
            for i in range(0, len(s64_list), chunk_size):
                chunk = s64_list[i:i+chunk_size]
                try:
                    url = 'https://steamhistory.net/api/sourcebans'
                    params = {'key': key, 'steamids': ','.join(chunk), 'shouldkey': 1}
                    resp = requests.get(url, params=params, timeout=5)
                    data = resp.json()

                    if 'response' in data and isinstance(data['response'], dict):
                        updates = {}
                        for s64_str, bans in data['response'].items():
                            try:
                                sid3 = f"[U:1:{int(s64_str) - 76561197960265728}]"
                                updates[sid3] = bans if isinstance(bans, list) else []
                            except: pass

                        with self.steamhistory_lock:
                            self.steamhistory_bans.update(updates)

                except Exception as e:
                    print(f"SourceBans API Error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def get_sourcebans_count(self, steamid):
        with self.steamhistory_lock:
            bans = self.steamhistory_bans.get(steamid, [])
        relevant_bans = [b for b in bans if b.get('CurrentState') != 'Unbanned']
        return len(relevant_bans) if relevant_bans else ""

    def get_sourcebans_details(self, steamid):
        with self.steamhistory_lock:
            return self.steamhistory_bans.get(steamid, [])

    def mark_player(self, steamid, ptype, name=None, notes=None):
        self.lists.save_user_entry(steamid, ptype, notes, player_name=name)

    def delete_player(self, steamid):
        self.lists.delete_user(steamid)

    def mark_recently_played(self, steamid, ptype, recent_list_ref):
        self.lists.mark_recently_played(steamid, ptype, recent_list_ref)
