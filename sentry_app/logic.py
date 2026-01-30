import threading
import time
import requests
import datetime
from collections import deque, defaultdict
from .config import ConfigManager
from .rcon import RConManager
from .list_manager import ListManager
from .tf2_monitor import TF2Monitor
from .utils import convert_steamid3_to_steamid64, convert_steamid64_to_steamid3
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
        self.chat_msg_ttl = 30.0
        self.chat_fail_backoff = 1.5
        self.chat_fail_max = 3
        self.session_seen_players = set()
        self.announced_party_cheaters = set()
        self.announced_party_bans = set()
        self.suspicious_steamids = set()
        self.cached_detected_steamid = None

        self.last_kick_time = 0.0
        self.vote_next_allowed_time = 0.0
        self.vote_creation_cooldown = 170.0
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
        self.friend_cache = {}
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

    def get_suspicious_snapshot(self):
        with self.state_lock:
            return set(self.suspicious_steamids)

    def get_steamhistory_bans_snapshot(self, steamid):
        with self.steamhistory_lock:
            bans = self.steamhistory_bans.get(steamid)
            return list(bans) if isinstance(bans, list) else None

    def update_steam_api_data(self, steamids):
        api_key = self.get_setting("Steam_API_Key")
        if not api_key or len(api_key) < 10:
            return

        now = time.monotonic()
        to_query_summary = []
        to_query_bans = []
        to_query_playtime = []
        to_query_friends = []

        refresh_interval = 1800.0
        retry_interval = 30.0

        with self.steam_api_lock:
            for sid in steamids:
                entry = self.steam_api_cache.setdefault(sid, {})

                last_success = entry.get('last_success', 0.0)
                last_attempt = entry.get('last_attempt', 0.0)

                stale = (now - last_success) > refresh_interval
                can_retry = (now - last_attempt) > retry_interval

                if stale and can_retry:
                    to_query_summary.append(sid)
                    to_query_bans.append(sid)
                    entry['last_attempt'] = now

                if 'playtime' not in entry:
                    to_query_playtime.append(sid)
                    entry['playtime'] = None

                f_entry = self.friend_cache.get(sid)
                if not f_entry:
                    to_query_friends.append(sid)
                    self.friend_cache[sid] = {'friends': set(), 'last_update': now}

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

        sid_map_play = get_map(to_query_playtime[:20])
        for s64, sid3 in sid_map_play.items():
            self.api_executor.submit(self._worker_single_playtime, api_key, s64, sid3)

        sid_map_friends = get_map(to_query_friends[:20])
        for s64, sid3 in sid_map_friends.items():
            self.api_executor.submit(self._worker_single_friends, api_key, s64, sid3)


    def _worker_batch_api(self, key, map_summ, map_bans):
        now = time.monotonic()

        if map_summ:
            try:
                ids = list(map_summ.keys())
                for i in range(0, len(ids), 100):
                    chunk = ids[i:i+100]
                    r = requests.get(
                        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/",
                        params={'key': key, 'steamids': ",".join(chunk)},
                        timeout=10
                    )
                    if r.status_code == 200:
                        for p in r.json().get('response', {}).get('players', []):
                            sid3 = map_summ.get(p['steamid'])
                            if sid3:
                                with self.steam_api_lock:
                                    e = self.steam_api_cache.setdefault(sid3, {})
                                    e['avatar'] = p.get('avatarfull')
                                    e['timecreated'] = p.get('timecreated', 0)
                                    e['last_success'] = now
                    else:
                        print(f"[API] GetPlayerSummaries failed: {r.status_code}")
            except Exception as e:
                print(f"[API] Summary Error: {e}")

        if map_bans:
            try:
                ids = list(map_bans.keys())
                for i in range(0, len(ids), 100):
                    chunk = ids[i:i+100]
                    r = requests.get(
                        "https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/",
                        params={'key': key, 'steamids': ",".join(chunk)},
                        timeout=10
                    )
                    if r.status_code == 200:
                        for b in r.json().get('players', []):
                            sid3 = map_bans.get(b['SteamId'])
                            if sid3:
                                with self.steam_api_lock:
                                    e = self.steam_api_cache.setdefault(sid3, {})
                                    e['vac'] = b.get('VACBanned', False)
                                    e['game_bans'] = b.get('NumberOfGameBans', 0)
                                    e['last_success'] = now
                    else:
                        print(f"[API] GetPlayerBans failed: {r.status_code}")
            except Exception as e:
                print(f"[API] Bans Error: {e}")

    def _worker_single_friends(self, key, s64, sid3):
        try:
            r = requests.get(
                "https://api.steampowered.com/ISteamUser/GetFriendList/v0001/",
                params={'key': key, 'steamid': s64, 'relationship': 'friend'},
                timeout=10
            )

            friends_s3 = set()
            visible = False

            if r.status_code == 200:
                data = r.json()
                if 'friendslist' in data and 'friends' in data['friendslist']:
                    visible = True
                    friends_s64 = [f['steamid'] for f in data['friendslist']['friends']]
                    for fs64 in friends_s64:
                        try:
                            conv = convert_steamid64_to_steamid3(fs64)
                            friends_s3.add(conv)
                        except:
                            pass

            with self.steam_api_lock:
                self.friend_cache[sid3] = {
                    'friends': friends_s3,
                    'visible': visible,
                    'last_update': time.monotonic()
                }
        except Exception:
            pass

    def calculate_stacks(self, all_players):
        p_map = {p.steamid: p for p in all_players}
        sids = list(p_map.keys())

        adj = defaultdict(set)

        with self.steam_api_lock:
            for sid in sids:
                f_data = self.friend_cache.get(sid)
                if f_data:
                    my_friends = f_data['friends']
                    online_friends = my_friends.intersection(sids)
                    for friend_sid in online_friends:
                        adj[sid].add(friend_sid)
                        adj[friend_sid].add(sid)

        visited = set()
        stack_id_counter = 1

        for sid in sids:
            if sid not in visited and sid in adj:
                stack_group = set()
                queue = [sid]
                visited.add(sid)

                while queue:
                    curr = queue.pop(0)
                    stack_group.add(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                if len(stack_group) > 1:
                    names_in_stack = [p_map[s].name for s in stack_group]
                    for s in stack_group:
                        p_map[s].stack_id = stack_id_counter

                        direct_friend_names = []
                        if s in adj:
                            for neighbor_sid in adj[s]:
                                if neighbor_sid in p_map:
                                    direct_friend_names.append(p_map[neighbor_sid].name)
                        p_map[s].direct_friends = direct_friend_names

                        extended_names = [n for n in names_in_stack if n != p_map[s].name and n not in direct_friend_names]
                        p_map[s].extended_stack = extended_names

                    stack_id_counter += 1

    def _worker_single_playtime(self, key, s64, sid3):
        try:
            r = requests.get("https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/",
                             params={'key': key, 'steamid': s64, 'format': 'json',
                                     'include_played_free_games': 1, 'appids_filter[0]': 440}, timeout=10)

            val = None
            if r.status_code == 200:
                data = r.json().get('response', {})
                if 'games' in data:
                    games = data.get('games', [])
                    tf2 = next((g for g in games if g['appid'] == 440), None)

                    if tf2:
                        minutes = tf2.get('playtime_forever', 0)
                        if minutes > 0:
                            val = minutes
                        else:
                            val = None

            with self.steam_api_lock:
                self.steam_api_cache.setdefault(sid3, {})['playtime'] = val

        except Exception:
            pass

    def annotate_friend_mark_stats(self, players):
        if not players:
            return

        with self.lists.lock:
            user_cheaters = set(self.lists.user_cheaters)
            user_suspicious = set(self.lists.user_suspicious)
            tf2bd_cheaters = set(self.lists.tf2bd_cheaters)
            tf2bd_suspicious = set(self.lists.tf2bd_suspicious)

            user_marked = user_cheaters | user_suspicious
            tf2bd_marked = tf2bd_cheaters | tf2bd_suspicious

        with self.steam_api_lock:
            fcache = {p.steamid: self.friend_cache.get(p.steamid) for p in players}

        for p in players:
            f_entry = fcache.get(p.steamid)

            p.friendlist_visible = None
            p.friend_count = None

            p.marked_friends_total = None
            p.marked_friends_user = None
            p.marked_friends_tf2bd = None

            p.marked_cheater_friends_user = None
            p.marked_suspicious_friends_user = None
            p.marked_cheater_friends_tf2bd = None
            p.marked_suspicious_friends_tf2bd = None

            if not f_entry:
                continue

            visible = f_entry.get('visible', None)

            if visible is None:
                continue

            if visible is False:
                p.friendlist_visible = False
                continue

            friends = f_entry.get('friends')
            if not isinstance(friends, set):
                friends = set()

            p.friendlist_visible = True
            p.friend_count = len(friends)

            u_marked = friends & user_marked
            t_marked = friends & tf2bd_marked
            p.marked_friends_user = len(u_marked)
            p.marked_friends_tf2bd = len(t_marked)
            p.marked_friends_total = len(u_marked | t_marked)

            p.marked_cheater_friends_user = len(friends & user_cheaters)
            p.marked_suspicious_friends_user = len(friends & user_suspicious)
            p.marked_cheater_friends_tf2bd = len(friends & tf2bd_cheaters)
            p.marked_suspicious_friends_tf2bd = len(friends & tf2bd_suspicious)

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
            p.mark_tooltip = self.lists.get_mark_tooltip(p.steamid)

        self.calculate_stacks(all_players)
        self.annotate_friend_mark_stats(all_players)
        now_ts = int(time.time())

        with self.steam_api_lock:
            for p in all_players:
                data = self.steam_api_cache.get(p.steamid, {})

                p.avatar_url = data.get('avatar')
                p.vac_banned = data.get('vac')
                p.game_bans = data.get('game_bans')
                p.tf2_playtime = data.get('playtime')

                created = data.get('timecreated', 0)
                if created > 0:
                    years = (now_ts - created) / 31536000
                    p.account_age = round(years, 1)
                else:
                    p.account_age = None

        with self.steamhistory_lock:
            api_key_exists = bool(self.get_setting("SteamHistory_API_Key"))
            for p in all_players:
                p.sb_details = self.steamhistory_bans.get(p.steamid)

                if p.sb_details is not None:
                    relevant = [b for b in p.sb_details if b.get('CurrentState') != 'Unbanned']
                    p.ban_count = len(relevant)
                elif not api_key_exists:
                    p.ban_count = None
                elif p.steamid in self.steamhistory_cache:
                    p.ban_count = 0
                else:
                    p.ban_count = None

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


    def _build_name_chunks(self, prefix, names, limit=120):
        chunks = []
        cur = prefix
        first_in_chunk = True

        for name in names:
            sep = "" if first_in_chunk else ", "
            candidate = cur + sep + name

            if len(candidate) <= limit:
                cur = candidate
                first_in_chunk = False
                continue
            if cur != prefix:
                chunks.append(cur)
            else:
                chunks.append((prefix + name)[:limit])

            cur = prefix + name
            first_in_chunk = False

            if len(cur) > limit:
                cur = cur[:limit]

        if cur and cur != prefix:
            chunks.append(cur)
        return chunks

    def _build_cheater_announcements(self, cheater_names, *, max_full_names=8, limit=120, prefix=None):
        total = len(cheater_names)
        if total == 0:
            return []

        if prefix is None:
            prefix = f"[Sentry] Found {total} cheater(s): "

        if total <= max_full_names:
            return self._build_name_chunks(prefix, cheater_names, limit=limit)

        return [self._format_cheater_compact(cheater_names, prefix=prefix, limit=limit)]

    def _format_cheater_compact(self, cheater_names, *, prefix, limit=120):
        total = len(cheater_names)
        if len(prefix) >= limit:
            return f"[Sentry] Found {total} cheater(s)."

        out = prefix
        shown = 0

        for i, name in enumerate(cheater_names):
            sep = "" if shown == 0 else ", "
            candidate = out + sep + name
            remaining_after = total - (i + 1)
            suffix = f" (+{remaining_after} more)" if remaining_after > 0 else ""

            if len(candidate + suffix) <= limit:
                out = candidate
                shown += 1
                continue

            if shown > 0:
                remaining = total - shown
                suf = f" (+{remaining} more)"
                if len(prefix + suf) <= limit:
                    return prefix.rstrip() + suf
                return f"[Sentry] Found {total} cheater(s)."
            else:
                return f"[Sentry] Found {total} cheater(s)."

        return out

    def queue_chat_chunks(self, chunks, chat_type):
        valid_chat_types = {'say', 'tf_party_chat', 'say_team'}
        if chat_type not in valid_chat_types:
            return
        if not chunks:
            return

        CHUNK_SIZE = 120
        clean = []
        for c in chunks:
            if not c:
                continue
            if len(c) <= CHUNK_SIZE:
                clean.append(c)
            else:
                clean.extend([c[i:i+CHUNK_SIZE] for i in range(0, len(c), CHUNK_SIZE)])

        if not clean:
            return

        now = time.monotonic()
        with self.state_lock:
            new_q = deque(b for b in self.chat_queue if b['chat_type'] != chat_type)
            self.chat_queue = new_q

            self.chat_queue.append({
                'chat_type': chat_type,
                'chunks': clean,
                'idx': 0,
                'enq_ts': now,
                'fails': 0
            })

    def queue_chat(self, msg, chat_type):
        CHUNK_SIZE = 120
        chunks = [msg[i:i + CHUNK_SIZE] for i in range(0, len(msg), CHUNK_SIZE)]
        self.queue_chat_chunks(chunks, chat_type)

    def _process_chat_queue(self):
        with self.state_lock:
            if not self.chat_queue:
                return

            now = time.monotonic()
            if (now - self.last_chat_time) < self.chat_delay:
                return

            while self.chat_queue:
                b = self.chat_queue[0]
                if b['idx'] == 0 and (now - b['enq_ts']) > self.chat_msg_ttl:
                    self.chat_queue.popleft()
                    continue
                break

            if not self.chat_queue:
                return

            b = self.chat_queue[0]
            idx = b['idx']
            if idx >= len(b['chunks']):
                self.chat_queue.popleft()
                return

            chat_type = b['chat_type']
            message = b['chunks'][idx]

            last_sent = self._chat_recent.get((chat_type, message), 0.0)
            if last_sent and (now - last_sent) < self._chat_recent_ttl:
                b['idx'] += 1
                if b['idx'] >= len(b['chunks']):
                    self.chat_queue.popleft()
                return

        ok, _ = self.rcon.execute(f'{chat_type} "{message}"')

        with self.state_lock:
            if not self.chat_queue:
                return

            b = self.chat_queue[0]

            if ok:
                now2 = time.monotonic()
                self.last_chat_time = now2
                self._chat_recent[(chat_type, message)] = now2
                b['fails'] = 0
                b['idx'] += 1
                if b['idx'] >= len(b['chunks']):
                    self.chat_queue.popleft()

                if len(self._chat_recent) > 500:
                    self._chat_recent.clear()
            else:
                b['fails'] = b.get('fails', 0) + 1
                self.last_chat_time = time.monotonic() + self.chat_fail_backoff
                if b['fails'] >= self.chat_fail_max:
                    self.chat_queue.popleft()

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

    def kick_player(self, steamid, reason=""):
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
                    arg = str(target_uid)
                    if reason:
                        arg += f" {reason}"
                    cmd = f'callvote kick "{arg}"'

                    self.rcon.execute(cmd)
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

        now = time.monotonic()
        if now < self.vote_next_allowed_time:
            return

        with self.state_lock:
            if self.user_current_team == "Red":
                target_list = list(self.connected_red_players)
            elif self.user_current_team == "Blue":
                target_list = list(self.connected_blue_players)
            else:
                return

        for p in target_list:
            if p.player_type == "Cheater":
                started = self.kick_player(p.steamid, "cheating")
                if started:
                    self.vote_next_allowed_time = now + self.vote_creation_cooldown
                break

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

        cheaters = [p.name for p in all_p if p.player_type == "Cheater"]
        if cheaters:
            chunks = self._build_cheater_announcements(cheaters, max_full_names=8, limit=120)
            self.queue_chat_chunks(chunks, "say")
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
                    if p.steamid in self.announced_party_cheaters:
                        continue
                    if p.player_type == "Cheater":
                        new_cheaters.append(p.name)
                        self.announced_party_cheaters.add(p.steamid)

            if new_cheaters:
                prefix = f"[Sentry] Cheaters found ({len(new_cheaters)}): "
                chunks = self._build_cheater_announcements(
                    new_cheaters,
                    max_full_names=8,
                    limit=120,
                    prefix=prefix
                )
                self.queue_chat_chunks(chunks, "tf_party_chat")

        if self.get_setting_bool("Party_Announce_Bans"):
            new_sus = []
            with self.state_lock:
                for p in all_players:
                    if p.steamid in self.suspicious_steamids and p.steamid not in self.announced_party_bans:
                        new_sus.append(p.name)
                        self.announced_party_bans.add(p.steamid)

            if new_sus:
                prefix = f"[Sentry] Possible cheaters (Sourceban keyword match) ({len(new_sus)}): "
                chunks = self._build_cheater_announcements(
                    new_sus,
                    max_full_names=8,
                    limit=120,
                    prefix=prefix
                )
                self.queue_chat_chunks(chunks, "tf_party_chat")

    def update_sourcebans(self, steamids):
        key = self.get_setting("SteamHistory_API_Key")
        if not key:
            return

        now = time.time()

        refresh_interval = 86400.0
        retry_interval = 60.0

        to_query = []
        with self.steamhistory_lock:
            for sid in steamids:
                entry = self.steamhistory_cache.setdefault(sid, {})
                last_success = entry.get('last_success', 0.0)
                last_attempt = entry.get('last_attempt', 0.0)

                stale = (now - last_success) > refresh_interval
                can_retry = (now - last_attempt) > retry_interval

                if stale and can_retry:
                    to_query.append(sid)
                    entry['last_attempt'] = now

        if not to_query:
            return

        def worker():
            s64_list = []
            sid3_by_s64 = {}
            for s in to_query:
                conv = convert_steamid3_to_steamid64(s)
                if conv:
                    s64 = str(conv)
                    s64_list.append(s64)
                    sid3_by_s64[s64] = s

            if not s64_list:
                return

            chunk_size = 100
            for i in range(0, len(s64_list), chunk_size):
                chunk = s64_list[i:i+chunk_size]
                try:
                    url = 'https://steamhistory.net/api/sourcebans'
                    params = {'key': key, 'steamids': ','.join(chunk), 'shouldkey': 1}
                    resp = requests.get(url, params=params, timeout=5)
                    resp.raise_for_status()
                    data = resp.json()

                    if 'response' in data and isinstance(data['response'], dict):
                        updates = {}
                        success_sids = set()

                        for s64_str, bans in data['response'].items():
                            sid3 = sid3_by_s64.get(s64_str)
                            if not sid3:
                                continue
                            updates[sid3] = bans if isinstance(bans, list) else []
                            success_sids.add(sid3)

                        with self.steamhistory_lock:
                            self.steamhistory_bans.update(updates)
                            tnow = time.time()
                            for sid3 in success_sids:
                                ent = self.steamhistory_cache.setdefault(sid3, {})
                                ent['last_success'] = tnow

                except Exception as e:
                    print(f"SourceBans API Error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def get_sourcebans_count(self, steamid):
        key = self.get_setting("SteamHistory_API_Key")
        if not key: return None
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

    def get_player_by_steamid(self, steamid):
        with self.state_lock:
            all_current = (self.connected_red_players +
                        self.connected_blue_players +
                        self.connected_spectator_players +
                        self.connected_unassigned_players)
            for p in all_current:
                if p.steamid == steamid:
                    return p

            for p in self.recently_played:
                if p.steamid == steamid:
                    return p
        return None
