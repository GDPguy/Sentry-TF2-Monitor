import os
import json
import time
import hashlib
import threading
import datetime
import requests
from .utils import atomic_write_bytes, convert_steamid64_to_steamid3
from .models import PlayerInstance
from .consts import BUILTIN_TF2BD_LISTS


class ListManager:
    # File that stores per-list settings (enabled / auto_update / url /
    # filename) for both built-in and user-added lists. Built-ins start
    # with defaults (enabled + auto_update) the first time the user runs
    # the app; toggles here override the defaults.
    LISTS_CONFIG_FILENAME = 'tf2bd_lists.json'

    def __init__(self, config_manager, state_lock):
        self.cfg = config_manager
        self.lock = state_lock

        self.cfg_dir = 'cfg'
        self.tf2bd_dir = 'tf2bd_lists'
        self.userlist_path = os.path.join(self.cfg_dir, 'userlist.json')
        self.lists_config_path = os.path.join(self.cfg_dir, self.LISTS_CONFIG_FILENAME)

        self.tf2bd_data = {}
        self.tf2bd_cheaters = []
        self.tf2bd_suspicious = []

        self.user_entries = []
        self.user_cheaters = []
        self.user_suspicious = []
        self.user_other = []
        self.user_notes_map = {}

        self.userlist_error = None
        self.tf2bd_error = None

        # Ordered list of dicts: {name, url, filename, enabled, auto_update,
        # is_builtin, last_updated, last_status, last_player_count}. The
        # UI reads/writes this through the methods below; the file scan in
        # _read_tf2bd_lists() is the source of truth for player contents,
        # but this list decides which URLs we fetch and what we display.
        self.lists_config = []

        # Status of the last auto-update / bootstrap run. The UI reads this
        # so the user can see what happened (instead of getting silent
        # print()s into a --noconsole build).
        self.last_update_status = ""

        self._ensure_dirs()
        self._load_lists_config()

    def _ensure_dirs(self):
        os.makedirs(self.cfg_dir, exist_ok=True)
        os.makedirs(self.tf2bd_dir, exist_ok=True)
        if not os.path.exists(self.userlist_path):
            with open(self.userlist_path, 'w', encoding='utf-8') as f:
                f.write('[]')

    def load_all(self):
        self.load_tf2bd_data()
        self.load_user_entries()

    # --- TF2BD lists config (cfg/tf2bd_lists.json) -------------------------
    #
    # Each entry is a dict:
    #   {name, url, filename, enabled, auto_update, is_builtin,
    #    last_updated (epoch), last_status (str), last_player_count (int)}
    #
    # Built-ins live in BUILTIN_TF2BD_LISTS in consts.py and get added the
    # first time the app runs (or whenever a new build of Sentry introduces
    # a new built-in). User-added entries live in the JSON file with
    # is_builtin=False and can be removed.

    def _load_lists_config(self):
        """Load cfg/tf2bd_lists.json. On first run (or after an upgrade that
        added new built-ins), seed it with the BUILTIN_TF2BD_LISTS so the UI
        shows a sensible default. Existing user entries are preserved."""
        try:
            with open(self.lists_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or 'lists' not in data:
                data = {'lists': []}
        except (FileNotFoundError, json.JSONDecodeError):
            data = {'lists': []}

        # Merge in built-ins: any built-in that isn't already represented
        # in the saved config gets added (with default enabled/auto_update).
        existing_urls = {entry.get('url') for entry in data['lists']}
        for name, url, filename in BUILTIN_TF2BD_LISTS:
            if url not in existing_urls:
                data['lists'].append({
                    'name': name,
                    'url': url,
                    'filename': filename,
                    'enabled': True,
                    'auto_update': True,
                    'is_builtin': True,
                    'last_updated': 0.0,
                    'last_status': '',
                    'last_player_count': 0,
                })
            else:
                # Make sure is_builtin is set correctly (in case the user
                # hand-edited the file).
                for entry in data['lists']:
                    if entry.get('url') == url:
                        entry['is_builtin'] = True
                        break

        self.lists_config = data['lists']
        self._save_lists_config()

    def _save_lists_config(self):
        try:
            atomic_write_bytes(
                self.lists_config_path,
                json.dumps({'lists': self.lists_config}, indent=2).encode('utf-8'),
            )
        except Exception as e:
            print(f"Error saving lists config: {e}")

    def get_lists(self):
        """Return a deep-ish copy of the lists config for the UI to render.
        Mutations go back through set_list_* / add_custom_list / remove_list."""
        return [dict(entry) for entry in self.lists_config]

    def _find_list_index(self, url):
        for i, entry in enumerate(self.lists_config):
            if entry.get('url') == url:
                return i
        return -1

    def set_list_enabled(self, url, enabled):
        i = self._find_list_index(url)
        if i < 0: return False
        self.lists_config[i]['enabled'] = bool(enabled)
        self._save_lists_config()
        return True

    def set_list_auto_update(self, url, auto_update):
        i = self._find_list_index(url)
        if i < 0: return False
        self.lists_config[i]['auto_update'] = bool(auto_update)
        self._save_lists_config()
        return True

    def add_custom_list(self, name, url, enabled=True, auto_update=True):
        """Add a user-supplied list. Returns True on success, False if the
        URL is already present or invalid."""
        if not url or not isinstance(url, str):
            return False
        if self._find_list_index(url) >= 0:
            return False
        # Derive a local filename from the URL basename; fall back to a
        # sanitized version of the name if the URL has no obvious file.
        from urllib.parse import urlparse
        path = urlparse(url).path
        basename = os.path.basename(path.rstrip('/')) if path else ''
        if not basename or not basename.lower().endswith('.json'):
            safe = ''.join(c for c in name if c.isalnum() or c in ('-', '_')).strip()
            basename = f"playerlist.{safe or 'custom'}.json"

        self.lists_config.append({
            'name': name or basename,
            'url': url,
            'filename': basename,
            'enabled': bool(enabled),
            'auto_update': bool(auto_update),
            'is_builtin': False,
            'last_updated': 0.0,
            'last_status': '',
            'last_player_count': 0,
        })
        self._save_lists_config()
        return True

    def remove_list(self, url):
        """Remove a user-added list. Built-in lists cannot be removed (only
        disabled) to keep the curated defaults available across upgrades."""
        i = self._find_list_index(url)
        if i < 0: return False
        if self.lists_config[i].get('is_builtin'):
            return False
        # Also delete the local file so the list doesn't keep showing up
        # in the in-game tables after the user removes it.
        fn = self.lists_config[i].get('filename')
        if fn:
            fpath = os.path.join(self.tf2bd_dir, fn)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except OSError:
                pass
        del self.lists_config[i]
        self._save_lists_config()
        self._reload_tf2bd_from_disk()
        return True

    def _record_list_result(self, url, ok, status_msg, player_count):
        i = self._find_list_index(url)
        if i < 0: return
        self.lists_config[i]['last_updated'] = time.time()
        self.lists_config[i]['last_status'] = status_msg
        self.lists_config[i]['last_player_count'] = player_count
        self._save_lists_config()

    # --- end TF2BD lists config --------------------------------------------

    def load_tf2bd_data(self):
        self._reload_tf2bd_from_disk()
        if self.cfg.get_bool("Auto_Update_TF2BD_Lists"):
            threading.Thread(target=self._background_update_worker, daemon=True).start()

    def _background_update_worker(self):
        print("[Auto-Update] Starting background update...")
        messages = []

        # If the user has no lists yet, download the default ones first so
        # future runs of update_tf2bd_lists() have something to refresh.
        try:
            existing = [f for f in os.listdir(self.tf2bd_dir) if f.endswith('.json')]
            if not existing:
                boot_msgs = self.bootstrap_default_lists()
                messages.extend(boot_msgs)
        except Exception as e:
            messages.append(f"Bootstrap error: {e}")

        try:
            update_msgs = self.update_tf2bd_lists()
            messages.extend(update_msgs)
        except Exception as e:
            messages.append(f"Update error: {e}")

        try:
            self._reload_tf2bd_from_disk()
            messages.append("Lists reloaded.")
        except Exception as e:
            messages.append(f"Reload error: {e}")

        self.last_update_status = " | ".join(m for m in messages if m)
        print(f"[Auto-Update] {self.last_update_status}")

    def bootstrap_default_lists(self):
        """Download every enabled entry in self.lists_config that doesn't
        have a local file yet. Returns a list of human-readable status
        messages."""
        messages = []
        for entry in self.lists_config:
            if not entry.get('enabled', True):
                continue
            filename = entry.get('filename')
            if not filename:
                continue
            fpath = os.path.join(self.tf2bd_dir, filename)
            if os.path.exists(fpath):
                continue
            try:
                msg = self._download_list_to_file(entry['url'], filename)
                messages.append(msg)
            except Exception as e:
                messages.append(f"Failed to fetch {entry['url']}: {e}")
        return messages

    def _download_list_to_file(self, url, filename):
        """Fetch a single TF2BD-format JSON list from `url` and save it to
        tf2bd_lists/<filename>. Validates that it has the expected schema
        fields, preserves the URL as file_info.update_url so future
        auto-updates keep working, and returns a status string."""
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, dict) or 'players' not in data:
            raise ValueError(f"Response from {url} is not a valid TF2BD list (no 'players' field)")

        if 'file_info' not in data or not isinstance(data['file_info'], dict):
            data['file_info'] = {}
        # Preserve the URL so subsequent runs of update_tf2bd_lists() will
        # refresh this file in place instead of re-bootstrapping it.
        data['file_info']['update_url'] = url

        fpath = os.path.join(self.tf2bd_dir, filename)
        json_bytes = json.dumps(data, indent=2).encode('utf-8')
        atomic_write_bytes(fpath, json_bytes)

        title = data.get('file_info', {}).get('title', filename)
        n_players = len(data.get('players', []))
        self._record_list_result(url, True, f"Downloaded ({n_players} players)", n_players)
        return f"Downloaded {filename} ({n_players} players, title={title!r})"

    def force_update_now(self):
        """Run bootstrap + per-file update synchronously for all enabled
        lists and return a human-readable summary string. Intended for
        the UI's manual 'Update' button so the user sees something happen."""
        messages = []
        try:
            messages.extend(self.bootstrap_default_lists())
            messages.extend(self.update_tf2bd_lists())
            self._reload_tf2bd_from_disk()
            messages.append("Lists reloaded.")
        except Exception as e:
            messages.append(f"Error: {e}")
        self.last_update_status = " | ".join(m for m in messages if m)
        return self.last_update_status

    def _reload_tf2bd_from_disk(self):
        new_data, error_msg = self._read_tf2bd_lists()

        new_cheaters = []
        new_suspicious = []

        for sid, pdata in new_data.items():
            attrs = pdata.get('attributes', [])
            if 'cheater' in attrs: new_cheaters.append(sid)
            elif 'suspicious' in attrs: new_suspicious.append(sid)

        with self.lock:
            self.tf2bd_data = new_data
            self.tf2bd_cheaters = new_cheaters
            self.tf2bd_suspicious = new_suspicious
            self.tf2bd_error = error_msg

    def _read_tf2bd_lists(self):
        all_data = {}
        errors = []

        for fname in os.listdir(self.tf2bd_dir):
            if not fname.endswith('.json'): continue
            fpath = os.path.join(self.tf2bd_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'players' not in data:
                        continue

                    for p in data['players']:
                        sid = str(p.get('steamid'))
                        if sid.startswith('7656'):
                            sid = convert_steamid64_to_steamid3(sid)
                        if not sid: continue

                        proofs = p.get('proof', [])

                        if sid in all_data:
                            existing = all_data[sid]
                            if p.get('last_seen', {}).get('time', 0) > existing.get('last_seen', {}).get('time', 0):
                                existing['last_seen'] = p['last_seen']

                            existing['attributes'] = list(set(existing.get('attributes', []) + p.get('attributes', [])))

                            existing.setdefault('sources', []).append(fname)

                            if proofs:
                                existing.setdefault('proof_sources', {})[fname] = proofs
                        else:
                            all_data[sid] = {k:v for k,v in p.items() if k != 'steamid'}
                            all_data[sid]['sources'] = [fname]
                            if proofs:
                                all_data[sid]['proof_sources'] = {fname: proofs}

            except Exception as e:
                errors.append(f"{fname}: {e}")

        err_msg = None
        if errors:
            err_msg = "Failed to load some lists:\n" + "\n".join(errors[:5])
        return all_data, err_msg

    def update_tf2bd_lists(self):
        """For each enabled list with auto_update=True, refresh its file from
        the URL embedded in the file's own file_info.update_url (or, if
        missing, the URL stored in self.lists_config). Returns a list of
        human-readable status messages."""
        messages = []
        for entry in self.lists_config:
            if not entry.get('enabled', True):
                continue
            if not entry.get('auto_update', True):
                continue
            filename = entry.get('filename')
            if not filename:
                continue
            fpath = os.path.join(self.tf2bd_dir, filename)
            if not os.path.exists(fpath):
                # Skip silently - bootstrap_default_lists() handles downloads.
                continue
            msg = self._update_json_file(fpath, entry.get('url'))
            if msg:
                messages.append(msg)
                print(msg)
        return messages

    def _update_json_file(self, fpath, fallback_url=None):
        """Refresh fpath from its embedded file_info.update_url. If that's
        missing but fallback_url is provided, use that. Records the result
        on the matching lists_config entry. Returns a status string."""
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            url = data.get('file_info', {}).get('update_url') or fallback_url
            if not url:
                return None

            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            new_data = resp.json()

            old_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            new_hash = hashlib.sha256(json.dumps(new_data, sort_keys=True).encode()).hexdigest()

            if old_hash != new_hash:
                if 'file_info' not in new_data:
                    new_data['file_info'] = {}
                if 'update_url' not in new_data['file_info']:
                    new_data['file_info']['update_url'] = url

                json_bytes = json.dumps(new_data, indent=2).encode('utf-8')
                atomic_write_bytes(fpath, json_bytes)

                n_players = len(new_data.get('players', []))
                self._record_list_result(url, True, f"Updated ({n_players} players)", n_players)
                return f"Updated {os.path.basename(fpath)}"
            else:
                n_players = len(data.get('players', [])) if isinstance(data.get('players'), list) else 0
                self._record_list_result(url, True, "Already up to date", n_players)
                return f"{os.path.basename(fpath)}: already up to date"
        except Exception as e:
            msg = f"Error updating {os.path.basename(fpath)}: {e}"
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                url = d.get('file_info', {}).get('update_url') or fallback_url
                if url:
                    self._record_list_result(url, False, msg, 0)
            except Exception:
                pass
            return msg

    def load_user_entries(self):
        if not os.path.exists(self.userlist_path): return
        try:
            with open(self.userlist_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)

            clean_entries = []
            if isinstance(entries, list):
                for e in entries:
                    if 'steamid' in e and 'player_type' in e:
                        e.setdefault('last_seen_name', '')
                        e.setdefault('time_added', 0)
                        e.setdefault('time_last_seen', e['time_added'])
                        clean_entries.append(e)

            with self.lock:
                self.user_entries = clean_entries
                self._integrate_user_entries()

        except Exception as e:
            self.user_entries = []
            self.userlist_error = str(e)

    def _integrate_user_entries(self):
        self.user_cheaters.clear()
        self.user_suspicious.clear()
        self.user_other.clear()
        self.user_notes_map.clear()

        for e in self.user_entries:
            sid = e['steamid']
            ptype = e['player_type']
            self.user_notes_map[sid] = e.get('notes', "")

            if ptype == 'Cheater': self.user_cheaters.append(sid)
            elif ptype == 'Suspicious': self.user_suspicious.append(sid)
            elif ptype == 'Other': self.user_other.append(sid)

    def save_user_entry(self, steamid, player_type, notes, player_name=None, update_last_seen=False):
        save_names = self.cfg.get_bool('Save_Player_Names')
        save_times = self.cfg.get_bool('Save_Player_Timestamps')
        now = int(time.time())

        with self.lock:
            found = False
            for entry in self.user_entries:
                if entry['steamid'] == steamid:
                    entry['player_type'] = player_type
                    entry['notes'] = notes if notes is not None else entry.get('notes', "")
                    if player_name and save_names:
                        entry['last_seen_name'] = player_name
                    if update_last_seen and save_times:
                        entry['time_last_seen'] = now
                    found = True
                    break

            if not found:
                new_entry = {
                    "steamid": steamid,
                    "player_type": player_type,
                    "notes": notes or "",
                    "last_seen_name": player_name if (player_name and save_names) else "",
                    "time_added": now if save_times else 0,
                    "time_last_seen": now if save_times else 0
                }
                self.user_entries.append(new_entry)

            self._write_userlist()
            self._integrate_user_entries()

    def touch_user_entry(self, steamid, current_name):
        save_names = self.cfg.get_bool('Save_Player_Names')
        save_times = self.cfg.get_bool('Save_Player_Timestamps')
        if not (save_names or save_times): return

        dirty = False
        with self.lock:
            for entry in self.user_entries:
                if entry['steamid'] == steamid:
                    if save_times:
                        entry['time_last_seen'] = int(time.time())
                        dirty = True
                    if save_names and current_name and entry.get('last_seen_name') != current_name:
                        entry['last_seen_name'] = current_name
                        dirty = True
                    break
            if dirty:
                self._write_userlist()

    def delete_user(self, steamid):
        with self.lock:
            self.user_entries = [e for e in self.user_entries if e['steamid'] != steamid]
            self._write_userlist()
            self._integrate_user_entries()

    def _write_userlist(self):
        data = json.dumps(self.user_entries, indent=4).encode('utf-8')
        atomic_write_bytes(self.userlist_path, data)

    def update_recently_played(self, current_players, recent_list_ref):
        with self.lock:
            for p in current_players:
                existing = next((rp for rp in recent_list_ref if rp.steamid == p.steamid), None)
                if existing:
                    existing.name = p.name

                    if p.avatar_url: existing.avatar_url = p.avatar_url
                    if p.account_age is not None:
                        existing.account_age = p.account_age
                    if p.tf2_playtime is not None:
                        existing.tf2_playtime = p.tf2_playtime
                    if p.vac_banned is not None:
                        existing.vac_banned = p.vac_banned
                    if p.game_bans is not None:
                        existing.game_bans = p.game_bans
                    if p.ban_count is not None:
                        existing.ban_count = p.ban_count
                    if p.sb_details is not None:
                        existing.sb_details = p.sb_details
                    existing.player_type = p.player_type
                    existing.notes = p.notes
                else:
                    new_p = PlayerInstance(
                        p.userid, p.name, 0, p.steamid,
                        0, 0, p.player_type, p.notes, p.team
                    )
                    new_p.avatar_url = p.avatar_url
                    new_p.account_age = p.account_age
                    new_p.tf2_playtime = p.tf2_playtime
                    new_p.vac_banned = p.vac_banned
                    new_p.game_bans = p.game_bans

                    recent_list_ref.append(new_p)

    def mark_recently_played(self, steamid, ptype, recent_list_ref):
        with self.lock:
             for p in recent_list_ref:
                 if p.steamid == steamid:
                     p.player_type = ptype
                     self.save_user_entry(steamid, ptype, p.notes, player_name=p.name)
                     break

    def identify_player_type(self, steamid):
        with self.lock:
            if steamid in self.tf2bd_cheaters:
                return "Cheater"
            if steamid in self.tf2bd_suspicious:
                return "Suspicious"

            if steamid in self.user_cheaters:
                return "Cheater"
            if steamid in self.user_suspicious:
                return "Suspicious"
            if steamid in self.user_other:
                return "Other"
        return None

    def get_user_mark(self, steamid):
        with self.lock:
            if steamid in self.user_cheaters: return "Cheater"
            if steamid in self.user_suspicious: return "Suspicious"
            if steamid in self.user_other: return "Other"
        return None

    def get_mark_label(self, steamid):
        with self.lock:
            in_tf2bd = (steamid in self.tf2bd_cheaters or steamid in self.tf2bd_suspicious)
            in_user = (steamid in self.user_cheaters or steamid in self.user_suspicious or steamid in self.user_other)

            if in_tf2bd and in_user: return "[Both]"
            if in_tf2bd: return "[TF2BD]"
            if in_user: return "[User]"
        return ""

    def get_mark_tooltip(self, steamid):
        lines = []
        with self.lock:
            if steamid in self.tf2bd_cheaters: lines.append("TF2BD: Cheater")
            elif steamid in self.tf2bd_suspicious: lines.append("TF2BD: Suspicious")

            if steamid in self.user_cheaters: lines.append("User: Cheater")
            elif steamid in self.user_suspicious: lines.append("User: Suspicious")
            elif steamid in self.user_other: lines.append("User: Other")
        return "\n".join(lines)

    def get_user_notes(self, steamid):
        with self.lock:
            return self.user_notes_map.get(steamid, "")

    def is_in_userlist(self, steamid):
        with self.lock:
            return (steamid in self.user_cheaters or
                    steamid in self.user_suspicious or
                    steamid in self.user_other)

    def get_tf2bd_notes(self, steamid):
        if steamid not in self.tf2bd_data: return "No TF2BD data."
        d = self.tf2bd_data[steamid]
        lines = []

        lines.append(f"Attributes: {', '.join(d.get('attributes', []))}")

        if 'last_seen' in d:
             ls = d['last_seen']
             ts = datetime.datetime.fromtimestamp(ls.get('time', 0))
             lines.append(f"Last Seen: {ls.get('player_name')} at {ts}")

        lines.append("")

        proof_sources = d.get('proof_sources', {})

        if not proof_sources and 'proof' in d:
             p_flat = d['proof']
             if isinstance(p_flat, list):
                 lines.append(f"Proof: {'; '.join(p_flat)}")
             else:
                 lines.append(f"Proof: {p_flat}")

        for src, proofs in proof_sources.items():
            lines.append(f"[{src}]")
            for p in proofs:
                lines.append(f"- {p}")
            lines.append("")

        return "\n".join(lines).strip()

    def export_to_tf2bd(self, path):
        out = {
            "$schema": "https://raw.githubusercontent.com/PazerOP/tf2_bot_detector/master/schemas/v3/playerlist.schema.json",
            "file_info": {
                "authors": ["Sentry User"],
                "description": "Exported player list from Sentry",
                "title": "Sentry Export",
                "update_url": ""
            },
            "players": []
        }

        count = 0
        with self.lock:
            for e in self.user_entries:
                pt = e.get('player_type')

                attr = None
                if pt == 'Cheater': attr = 'cheater'
                elif pt == 'Suspicious': attr = 'suspicious'

                if not attr: continue

                p_obj = {
                    "steamid": e['steamid'],
                    "attributes": [attr]
                }

                notes = e.get('notes', '').strip()
                if notes:
                    p_obj['proof'] = [notes]

                ts = e.get('time_last_seen', 0)
                if ts == 0: ts = e.get('time_added', 0)

                name = e.get('last_seen_name', '')
                if ts > 0 and name and name != 'Unknown':
                    p_obj['last_seen'] = {
                        "time": ts,
                        "player_name": name
                    }

                out['players'].append(p_obj)
                count += 1

        try:
            json_bytes = json.dumps(out, indent=4).encode('utf-8')
            atomic_write_bytes(path, json_bytes)

            return True, f"Successfully exported {count} players."
        except Exception as e:
            return False, str(e)
