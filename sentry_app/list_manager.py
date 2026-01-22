# --- START OF FILE sentry_app/list_manager.py ---

import os
import json
import time
import hashlib
import threading
import datetime
import requests
from .utils import atomic_write_bytes, convert_steamid64_to_steamid3
from .models import PlayerInstance

class ListManager:
    def __init__(self, config_manager, state_lock):
        self.cfg = config_manager
        self.lock = state_lock

        self.cfg_dir = 'cfg'
        self.tf2bd_dir = 'tf2bd_lists'
        self.userlist_path = os.path.join(self.cfg_dir, 'userlist.json')

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

        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self.cfg_dir, exist_ok=True)
        os.makedirs(self.tf2bd_dir, exist_ok=True)
        if not os.path.exists(self.userlist_path):
            with open(self.userlist_path, 'w', encoding='utf-8') as f:
                f.write('[]')

    def load_all(self):
        self.load_tf2bd_data()
        self.load_user_entries()

    def load_tf2bd_data(self):
        self._reload_tf2bd_from_disk()
        if self.cfg.get_bool("Auto_Update_TF2BD_Lists"):
            threading.Thread(target=self._background_update_worker, daemon=True).start()

    def _background_update_worker(self):
        print("[Auto-Update] Starting background update...")
        try:
            self.update_tf2bd_lists()
            print("[Auto-Update] Update complete. Reloading lists...")
            self._reload_tf2bd_from_disk()
            print("[Auto-Update] Lists reloaded successfully.")
        except Exception as e:
            print(f"[Auto-Update] Error: {e}")

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

                        if sid in all_data:
                            existing = all_data[sid]
                            if p.get('last_seen', {}).get('time', 0) > existing.get('last_seen', {}).get('time', 0):
                                existing['last_seen'] = p['last_seen']
                            existing['proof'] = list(set(existing.get('proof', []) + p.get('proof', [])))
                            existing['attributes'] = list(set(existing.get('attributes', []) + p.get('attributes', [])))
                            existing.setdefault('sources', []).append(fname)
                        else:
                            all_data[sid] = {k:v for k,v in p.items() if k != 'steamid'}
                            all_data[sid]['sources'] = [fname]

            except Exception as e:
                errors.append(f"{fname}: {e}")

        err_msg = None
        if errors:
            err_msg = "Failed to load some lists:\n" + "\n".join(errors[:5])
        return all_data, err_msg

    def update_tf2bd_lists(self):
        print("[Auto-Update] Checking TF2BD lists...")
        for fname in os.listdir(self.tf2bd_dir):
            if fname.endswith('.json'):
                self._update_json_file(os.path.join(self.tf2bd_dir, fname))

    def _update_json_file(self, fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            url = data.get('file_info', {}).get('update_url')
            if not url: return

            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            new_data = resp.json()

            old_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            new_hash = hashlib.sha256(json.dumps(new_data, sort_keys=True).encode()).hexdigest()

            if old_hash != new_hash:
                new_data['file_info'] = data.get('file_info', {})

                json_bytes = json.dumps(new_data, indent=2).encode('utf-8')
                atomic_write_bytes(fpath, json_bytes)

                print(f"Updated {os.path.basename(fpath)}")
        except Exception as e:
            print(f"Error updating {os.path.basename(fpath)}: {e}")

    def load_user_entries(self):
        if not os.path.exists(self.userlist_path): return
        try:
            with open(self.userlist_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)

            clean_entries = []
            if isinstance(entries, list):
                for e in entries:
                    if 'steamid' in e and 'player_type' in e:
                        e.setdefault('last_seen_name', 'Unknown')
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
                    "last_seen_name": player_name if (player_name and save_names) else "Unknown",
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
                    if p.name: existing.name = p.name
                    existing.player_type = p.player_type
                    existing.notes = p.notes
                else:
                    new_p = PlayerInstance(
                        p.userid, p.name, p.ping, p.steamid,
                        p.kills, p.deaths, p.player_type, p.notes, p.team
                    )
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
            if steamid in self.tf2bd_cheaters or steamid in self.user_cheaters:
                return "Cheater"
            if steamid in self.tf2bd_suspicious or steamid in self.user_suspicious:
                return "Suspicious"
            if steamid in self.user_other:
                return "Other"
        return None

    def get_mark_label(self, steamid):
        with self.lock:
            in_tf2bd = (steamid in self.tf2bd_cheaters or steamid in self.tf2bd_suspicious)
            in_user = (steamid in self.user_cheaters or steamid in self.user_suspicious or steamid in self.user_other)

            if in_tf2bd and in_user: return "[Both]"
            if in_tf2bd: return "[TF2BD]"
            if in_user: return "[User]"
        return ""

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
        if 'proof' in d: lines.append(f"Proof: {d['proof']}")
        if 'last_seen' in d:
             ls = d['last_seen']
             ts = datetime.datetime.fromtimestamp(ls.get('time', 0))
             lines.append(f"Last Seen: {ls.get('player_name')} at {ts}")
        return "\n".join(lines)

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

                if ts > 0:
                    p_obj['last_seen'] = {
                        "time": ts,
                        "player_name": e.get('last_seen_name', 'Unknown')
                    }

                out['players'].append(p_obj)
                count += 1

        try:
            json_bytes = json.dumps(out, indent=4).encode('utf-8')
            atomic_write_bytes(path, json_bytes)

            return True, f"Successfully exported {count} players."
        except Exception as e:
            return False, str(e)
