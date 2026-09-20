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
    LISTS_CONFIG_FILENAME = 'tf2bd_lists.json'
    LIST_NAME_MAX_LENGTH = 80
    LIST_URL_MAX_LENGTH = 2048

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

        # Configured TF2BD lists are user-selected sources. Existing JSON files
        # already present in tf2bd_lists/ are imported into this config so
        # upgrades do not stop loading lists users already trust.
        self.lists_config = []
        self.last_update_status = ""
        self.last_update_changed_data = False
        self.last_add_error = ""
        self._update_lock = threading.Lock()
        # True from just before the startup updater thread is launched until all
        # startup list I/O/config writes are finished. The TF2BD manager uses
        # this to avoid reading/editing list config while that worker is active.
        self._startup_update_running = False
        self._loaded_enabled_files = set()
        self._loaded_file_signatures = {}
        self._runtime_data_files_changed = False
        # Once the user declines the restart prompt, do not nag again for the
        # same pending-restart session. This resets automatically if the disk/config
        # state returns to the currently loaded TF2BD snapshot.
        self._restart_prompt_suppressed = False

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

    # --- TF2BD lists config -------------------------------------------------

    def _load_lists_config(self):
        """Load per-list settings and import any existing local list files."""
        try:
            with open(self.lists_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {'lists': []}

        raw_lists = data.get('lists', []) if isinstance(data, dict) else []
        if not isinstance(raw_lists, list):
            raw_lists = []

        cleaned = []
        seen_filenames = set()

        for entry in raw_lists:
            if not isinstance(entry, dict):
                continue

            filename = os.path.basename(str(entry.get('filename', '')).strip())
            if not filename or not filename.lower().endswith('.json'):
                continue

            filename_key = filename.lower()
            if filename_key in seen_filenames:
                continue

            url = str(entry.get('url', '') or '').strip()
            cleaned.append({
                'name': str(entry.get('name') or filename),
                'url': url,
                'filename': filename,
                'enabled': bool(entry.get('enabled', True)),
                'auto_update': bool(entry.get('auto_update', bool(url))),
                'last_updated': float(entry.get('last_updated', 0.0) or 0.0),
                'last_status': str(entry.get('last_status', '') or ''),
                'last_player_count': int(entry.get('last_player_count', 0) or 0),
            })
            seen_filenames.add(filename_key)

        self.lists_config = cleaned
        self._sync_config_with_existing_files()
        self._save_lists_config()

    def _sync_config_with_existing_files(self):
        """Add untracked JSON files from tf2bd_lists/ to the managed list UI.

        This preserves the old workflow where users manually dropped trusted
        TF2BD lists into the folder before per-list configuration existed.
        """
        known = {
            str(entry.get('filename', '')).lower()
            for entry in self.lists_config
            if entry.get('filename')
        }
        added_count = 0

        try:
            filenames = os.listdir(self.tf2bd_dir)
        except OSError:
            return False

        for fname in filenames:
            if not fname.lower().endswith('.json'):
                continue
            if fname.lower() in known:
                continue

            fpath = os.path.join(self.tf2bd_dir, fname)
            name = os.path.splitext(fname)[0]
            url = ''
            player_count = 0

            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get('players'), list):
                    continue

                info = data.get('file_info', {})
                if isinstance(info, dict):
                    name = str(info.get('title') or name)
                url = self._extract_list_update_url(data)
                player_count = len(data['players'])
            except Exception:
                # Leave malformed JSON for the loader to report rather than
                # silently registering it as a valid managed list.
                continue

            self.lists_config.append({
                'name': name,
                'url': url,
                'filename': fname,
                'enabled': True,
                'auto_update': bool(url),
                'last_updated': 0.0,
                'last_status': 'Existing local list' if url else 'No update URL',
                'last_player_count': player_count,
            })
            known.add(fname.lower())
            added_count += 1

        return added_count

    def sync_lists_from_disk(self):
        """Import newly-added local TF2BD JSON files without touching live player data."""
        added_count = self._sync_config_with_existing_files()
        if added_count:
            self._save_lists_config()
        return added_count

    def refresh_lists_from_disk(self):
        """Rescan tf2bd_lists/ and refresh file-derived metadata.

        This never changes the active in-memory TF2BD snapshot. Newly discovered
        files are registered for the next Sentry start.
        """
        added_count = self._sync_config_with_existing_files()
        metadata_changed = False

        for entry in self.lists_config:
            filename = entry.get('filename')
            if not filename:
                continue
            fpath = os.path.join(self.tf2bd_dir, filename)
            if not os.path.isfile(fpath):
                if entry.get('last_status') != 'File missing' or entry.get('last_player_count', 0) != 0:
                    entry['last_status'] = 'File missing'
                    entry['last_player_count'] = 0
                    metadata_changed = True
                continue

            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                players = data.get('players') if isinstance(data, dict) else None
                if not isinstance(players, list):
                    continue
                count = len(players)
                if entry.get('last_player_count', 0) != count:
                    entry['last_player_count'] = count
                    metadata_changed = True

                # Current list state takes precedence over stale update results.
                # A missing file is handled above; once present again, a disabled
                # updater should not keep showing an old 404 forever.
                if not entry.get('url'):
                    desired_status = 'No update URL'
                elif not entry.get('auto_update', True):
                    desired_status = 'Updates disabled'
                elif entry.get('last_status') == 'File missing':
                    desired_status = 'Existing local list'
                else:
                    desired_status = entry.get('last_status', '')

                if entry.get('last_status') != desired_status:
                    entry['last_status'] = desired_status
                    metadata_changed = True
            except Exception:
                continue

        if added_count or metadata_changed:
            self._save_lists_config()
        return added_count

    def _save_lists_config(self):
        try:
            atomic_write_bytes(
                self.lists_config_path,
                json.dumps({'lists': self.lists_config}, indent=2).encode('utf-8'),
            )
            return True
        except Exception as e:
            print(f"Error saving lists config: {e}")
            return False

    def get_lists(self):
        return [dict(entry) for entry in self.lists_config]

    def _current_enabled_file_set(self):
        return {
            str(entry.get('filename', '')).lower()
            for entry in self.lists_config
            if entry.get('enabled', True)
            and entry.get('filename')
            and os.path.isfile(os.path.join(self.tf2bd_dir, entry.get('filename')))
        }

    def _file_signature(self, fpath):
        """Return a signature for the player data that affects detection.

        Metadata-only changes such as title/update_url do not require the running
        process to restart because the active classification snapshot only depends
        on the players array.
        """
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            players = data.get('players') if isinstance(data, dict) else None
            if not isinstance(players, list):
                return None
            payload = json.dumps(players, sort_keys=True, separators=(',', ':')).encode('utf-8')
            return hashlib.sha256(payload).hexdigest()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _current_enabled_file_signatures(self):
        signatures = {}
        for entry in self.lists_config:
            if not entry.get('enabled', True):
                continue
            filename = str(entry.get('filename', '') or '')
            if not filename:
                continue
            fpath = os.path.join(self.tf2bd_dir, filename)
            signature = self._file_signature(fpath)
            if signature is not None:
                signatures[filename.lower()] = signature
        return signatures

    def _mark_runtime_file_changed(self, filename):
        if str(filename or '').lower() in self._loaded_enabled_files:
            self._runtime_data_files_changed = True

    def is_tf2bd_restart_required(self):
        """Whether enabled player data on disk differs from the loaded snapshot."""
        required = self._current_enabled_file_signatures() != self._loaded_file_signatures
        if not required:
            self._restart_prompt_suppressed = False
        return required

    def should_prompt_tf2bd_restart(self):
        return self.is_tf2bd_restart_required() and not self._restart_prompt_suppressed

    def suppress_tf2bd_restart_prompt(self):
        if self.is_tf2bd_restart_required():
            self._restart_prompt_suppressed = True

    def _find_list_index(self, filename):
        filename = str(filename or '').lower()
        for i, entry in enumerate(self.lists_config):
            if str(entry.get('filename', '')).lower() == filename:
                return i
        return -1

    def set_list_name(self, filename, name):
        i = self._find_list_index(filename)
        if i < 0:
            return False

        name = str(name or '').strip()
        if not name or len(name) > self.LIST_NAME_MAX_LENGTH:
            return False

        self.lists_config[i]['name'] = name
        self._save_lists_config()
        return True

    def _is_valid_update_url(self, url):
        url = str(url or '').strip()
        return (
            bool(url)
            and len(url) <= self.LIST_URL_MAX_LENGTH
            and url.startswith(('http://', 'https://'))
        )

    def _extract_list_update_url(self, data):
        if not isinstance(data, dict):
            return ''

        info = data.get('file_info')
        if not isinstance(info, dict):
            return ''

        update_url = str(info.get('update_url') or '').strip()
        if self._is_valid_update_url(update_url):
            return update_url
        return ''

    def set_list_enabled(self, filename, enabled):
        i = self._find_list_index(filename)
        if i < 0:
            return False

        self.lists_config[i]['enabled'] = bool(enabled)
        self._save_lists_config()
        return True

    def set_list_auto_update(self, filename, auto_update):
        i = self._find_list_index(filename)
        if i < 0:
            return False
        entry = self.lists_config[i]
        fpath = os.path.join(self.tf2bd_dir, entry.get('filename', ''))
        if not entry.get('url'):
            entry['auto_update'] = False
            if not os.path.isfile(fpath):
                entry['last_status'] = 'File missing'
                entry['last_player_count'] = 0
            else:
                entry['last_status'] = 'No update URL'
            self._save_lists_config()
            return not bool(auto_update)
        if not entry.get('enabled', True):
            return False

        entry['auto_update'] = bool(auto_update)
        if not os.path.isfile(fpath):
            entry['last_status'] = 'File missing'
            entry['last_player_count'] = 0
        elif auto_update:
            entry['last_status'] = 'Updates enabled'
        else:
            entry['last_status'] = 'Updates disabled'
        self._save_lists_config()
        return True

    def suggested_filename(self, name, url):
        from urllib.parse import urlparse
        path = urlparse(str(url or '')).path
        basename = os.path.basename(path.rstrip('/')) if path else ''
        if not basename or not basename.lower().endswith('.json'):
            safe = ''.join(c for c in str(name or '') if c.isalnum() or c in ('-', '_')).strip()
            basename = f"playerlist.{safe or 'custom'}.json"
        return basename

    def normalize_custom_filename(self, filename):
        raw = str(filename or '').strip()
        if not raw or '/' in raw or '\\' in raw:
            return None
        if any(ch in raw for ch in '<>:"|?*'):
            return None
        if raw.endswith((' ', '.')):
            return None
        if not raw.lower().endswith('.json'):
            raw += '.json'
        if raw in ('.json', '..json'):
            return None
        return raw

    def filename_in_use(self, filename):
        filename = self.normalize_custom_filename(filename)
        if not filename:
            return True
        key = filename.lower()
        if any(str(entry.get('filename', '')).lower() == key for entry in self.lists_config):
            return True
        try:
            return any(name.lower() == key for name in os.listdir(self.tf2bd_dir))
        except OSError:
            return False

    def next_available_filename(self, desired):
        desired = self.normalize_custom_filename(desired) or 'playerlist.custom.json'
        if not self.filename_in_use(desired):
            return desired
        stem, ext = os.path.splitext(desired)
        n = 2
        while True:
            candidate = f"{stem}.{n}{ext or '.json'}"
            if not self.filename_in_use(candidate):
                return candidate
            n += 1

    def add_custom_list(self, name, url, filename=None, enabled=True, auto_update=True):
        """Import a remote TF2BD list transactionally.

        The remote document is fetched and validated before either the list config
        or destination JSON file is created. A failed import leaves no list entry.
        """
        self.last_add_error = ""
        if not isinstance(url, str):
            self.last_add_error = 'Invalid URL.'
            return False
        url = url.strip()
        name = str(name or '').strip()
        if not name or len(name) > self.LIST_NAME_MAX_LENGTH:
            self.last_add_error = f'List names must be 1-{self.LIST_NAME_MAX_LENGTH} characters.'
            return False
        if len(url) > self.LIST_URL_MAX_LENGTH:
            self.last_add_error = f'URLs are limited to {self.LIST_URL_MAX_LENGTH} characters.'
            return False
        if not url.startswith(('http://', 'https://')):
            self.last_add_error = 'URL must start with http:// or https://.'
            return False
        matching_urls = [entry for entry in self.lists_config if entry.get('url') == url]
        if matching_urls:
            if len(matching_urls) == 1:
                self.last_add_error = 'That Update URL is already configured.'
            else:
                self.last_add_error = (
                    f'That Update URL is already configured for {len(matching_urls)} lists. '
                    "You probably don't need another copy."
                )
            return False

        filename = self.normalize_custom_filename(
            filename or self.suggested_filename(name, url)
        )
        if not filename:
            self.last_add_error = 'Invalid filename.'
            return False
        if self.filename_in_use(filename):
            self.last_add_error = f"The filename '{filename}' is already in use."
            return False

        try:
            data, effective_url = self._fetch_list_data(url, filename)

            # A list can advertise a canonical update_url that differs from the
            # URL the user pasted. Keep GUI imports from creating another copy of
            # a source that is already configured, while still allowing manually
            # dropped files with duplicate URLs to remain untouched.
            canonical_matches = [
                entry for entry in self.lists_config if entry.get('url') == effective_url
            ]
            if canonical_matches:
                if len(canonical_matches) == 1:
                    self.last_add_error = (
                        'The list advertises an Update URL that is already configured.'
                    )
                else:
                    self.last_add_error = (
                        'The list advertises an Update URL that is already configured for '
                        f"{len(canonical_matches)} lists. You probably don\'t need another copy."
                    )
                return False

            n_players = len(data['players'])
            fpath = os.path.join(self.tf2bd_dir, filename)
            atomic_write_bytes(fpath, json.dumps(data, indent=2).encode('utf-8'))
        except Exception as e:
            self.last_add_error = f'Failed to import list: {e}'
            return False

        entry = {
            'name': name,
            'url': effective_url,
            'filename': filename,
            'enabled': bool(enabled),
            'auto_update': bool(auto_update),
            'last_updated': time.time(),
            'last_status': f'Downloaded ({n_players} players)',
            'last_player_count': n_players,
        }
        self.lists_config.append(entry)
        if not self._save_lists_config():
            self.lists_config.pop()
            try:
                os.remove(fpath)
            except OSError:
                pass
            self.last_add_error = 'Could not save the list configuration.'
            return False
        return True

    def remove_list(self, filename):
        i = self._find_list_index(filename)
        if i < 0:
            return False

        entry = self.lists_config[i]
        fpath = os.path.join(self.tf2bd_dir, entry.get('filename', ''))
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
        except OSError:
            pass

        del self.lists_config[i]
        self._save_lists_config()
        return True

    def _record_list_result(self, filename, ok, status_msg, player_count=None):
        i = self._find_list_index(filename)
        if i < 0:
            return
        self.lists_config[i]['last_updated'] = time.time()
        self.lists_config[i]['last_status'] = status_msg
        # Preserve the last known good player count when an existing list fails
        # to update. A broken URL should not make a previously loaded count vanish.
        if player_count is not None:
            self.lists_config[i]['last_player_count'] = player_count
        self._save_lists_config()

    # --- end TF2BD lists config --------------------------------------------

    def load_tf2bd_data(self):
        self._reload_tf2bd_from_disk()
        # Reconcile persisted UI metadata before any background updater starts.
        # This clears stale update errors for lists whose updates are disabled,
        # while keeping File missing as the higher-priority state.
        self.refresh_lists_from_disk()
        if self.cfg.get_bool("Auto_Update_TF2BD_Lists"):
            # Set this before starting the thread so the UI cannot slip into the
            # tiny window between thread creation and the worker acquiring its lock.
            self._startup_update_running = True
            try:
                threading.Thread(
                    target=self._background_update_worker, daemon=True
                ).start()
            except Exception:
                self._startup_update_running = False
                raise

    def is_startup_update_running(self):
        """Return whether the initial automatic TF2BD update is still active."""
        return bool(self._startup_update_running)

    def _background_update_worker(self):
        print("[Auto-Update] Starting background update...")
        messages = []

        try:
            # Downloads are serialized, but the active TF2BD snapshot is deliberately
            # left alone. Newly downloaded data is used on the next Sentry start.
            with self._update_lock:
                try:
                    messages.extend(self.update_tf2bd_lists(respect_auto_update=True))
                    messages.extend(self.download_missing_lists(respect_auto_update=True))
                except Exception as e:
                    messages.append(f"Update error: {e}")

            if not messages:
                messages.append("No lists selected for automatic updates.")
            self.last_update_status = " | ".join(m for m in messages if m)
            # Print each result once. The previous flow printed individual update
            # lines and then printed the same messages again as one giant summary.
            for message in messages:
                if message:
                    print(f"[Auto-Update] {message}")
        finally:
            # Clear this only after all startup update/config work has completed.
            # A manager window waiting on this flag can now safely rescan disk.
            self._startup_update_running = False

    def download_missing_lists(self, respect_auto_update=False):
        """Download configured lists whose local file is missing.

        Startup and manual updates require both Enabled and Updates Enabled.
        Disabled lists are intentionally left untouched until re-enabled.
        """
        messages = []
        for entry in [dict(item) for item in self.lists_config]:
            if not entry.get('enabled', True):
                continue
            if respect_auto_update and not entry.get('auto_update', True):
                continue
            if not entry.get('url'):
                continue

            filename = entry.get('filename')
            if not filename:
                continue
            fpath = os.path.join(self.tf2bd_dir, filename)
            if os.path.exists(fpath):
                continue

            try:
                messages.append(self._download_list_to_file(entry))
            except Exception as e:
                msg = f"Failed to fetch {entry.get('name', filename)}: {e}"
                self._record_list_result(filename, False, msg, 0)
                messages.append(msg)
        return messages

    def _prepare_downloaded_data(self, data, configured_url, filename=None):
        if not isinstance(data, dict) or not isinstance(data.get('players'), list):
            raise ValueError("Response is not a valid TF2BD list (missing players array)")

        info = data.get('file_info')
        if not isinstance(info, dict):
            info = {}
            data['file_info'] = info

        # A list may move its own update endpoint. Follow any valid advertised
        # update_url after a successful fetch. The local filename is the stable
        # identity, so two configured files may safely point at the same source.
        advertised_url = self._extract_list_update_url(data)
        effective_url = advertised_url or configured_url

        info['update_url'] = effective_url
        return data, effective_url

    def _fetch_list_data(self, url, filename=None):
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return self._prepare_downloaded_data(resp.json(), url, filename)

    def _download_list_to_file(self, entry):
        url = entry.get('url', '')
        filename = entry.get('filename', '')
        if not url or not filename:
            raise ValueError("List is missing a URL or filename")

        data, effective_url = self._fetch_list_data(url, filename)

        fpath = os.path.join(self.tf2bd_dir, filename)
        atomic_write_bytes(fpath, json.dumps(data, indent=2).encode('utf-8'))
        self._mark_runtime_file_changed(filename)

        i = self._find_list_index(filename)
        if i >= 0 and effective_url != url:
            self.lists_config[i]['url'] = effective_url

        n_players = len(data['players'])
        self._record_list_result(
            filename, True,
            f"Downloaded ({n_players} players)", n_players,
        )
        return f"Downloaded {filename} ({n_players} players)"

    def force_update_list(self, filename):
        """Update one configured list

        This is an explicit per-list force update: Enabled and Updates Enabled
        are ignored. The list only needs a valid Update URL. Missing files are
        downloaded; existing files are refreshed.
        """
        self.last_update_changed_data = False

        i = self._find_list_index(filename)
        if i < 0:
            self.last_update_status = "Error: List not found."
            return self.last_update_status

        entry = dict(self.lists_config[i])
        if not entry.get('url'):
            self.last_update_status = "List does not have an update URL."
            return self.last_update_status
        with self._update_lock:
            fpath = os.path.join(self.tf2bd_dir, entry.get('filename', ''))
            if os.path.isfile(fpath):
                result = self._update_json_file(entry)
            else:
                try:
                    result = self._download_list_to_file(entry)
                except Exception as e:
                    result = f"Failed to fetch {entry.get('name', filename)}: {e}"
                    self._record_list_result(filename, False, result, 0)

        self.last_update_changed_data = str(result).startswith(("Updated ", "Downloaded "))
        self.last_update_status = result or ""
        return self.last_update_status

    def force_update_now(self):
        """Update configured list files on disk

        Manual updates only touch lists where both Enabled and Updates Enabled
        are selected. The running process keeps its existing TF2BD player snapshot;
        changed files take effect after a Sentry restart.
        """
        messages = []
        self.last_update_changed_data = False

        # Also notice JSON files the user may have copied into tf2bd_lists/
        # while Sentry is running. This only updates list configuration.
        self.sync_lists_from_disk()

        with self._update_lock:
            try:
                # Update files that already exist first, then fetch missing ones
                # so a newly downloaded list is not requested twice in one run.
                messages.extend(self.update_tf2bd_lists(respect_auto_update=True))
                messages.extend(self.download_missing_lists(respect_auto_update=True))
            except Exception as e:
                messages.append(f"Error: {e}")

        self.last_update_changed_data = any(
            str(msg).startswith(("Updated ", "Downloaded "))
            for msg in messages
        )
        if not messages:
            messages.append("No lists selected for updates.")
        self.last_update_status = " | ".join(m for m in messages if m)
        return self.last_update_status

    def _reload_tf2bd_from_disk(self):
        if self._sync_config_with_existing_files():
            self._save_lists_config()

        new_data, error_msg = self._read_tf2bd_lists()
        new_cheaters = []
        new_suspicious = []

        for sid, pdata in new_data.items():
            attrs = pdata.get('attributes', [])
            if 'cheater' in attrs:
                new_cheaters.append(sid)
            elif 'suspicious' in attrs:
                new_suspicious.append(sid)

        with self.lock:
            self.tf2bd_data = new_data
            self.tf2bd_cheaters = new_cheaters
            self.tf2bd_suspicious = new_suspicious
            self.tf2bd_error = error_msg

        # This is the stable player-list snapshot used for this process lifetime.
        self._loaded_enabled_files = self._current_enabled_file_set()
        self._loaded_file_signatures = self._current_enabled_file_signatures()
        self._runtime_data_files_changed = False
        # Once the user declines the restart prompt, do not nag again for the
        # same pending-restart session. This resets automatically if the disk/config
        # state returns to the currently loaded TF2BD snapshot.
        self._restart_prompt_suppressed = False

    def _read_tf2bd_lists(self):
        all_data = {}
        errors = []

        # Only configured + enabled lists participate in detection. Existing
        # files are imported into lists_config by _sync_config_with_existing_files().
        entries = [
            dict(entry) for entry in self.lists_config
            if entry.get('enabled', True) and entry.get('filename')
        ]

        for entry in entries:
            fname = entry['filename']
            fpath = os.path.join(self.tf2bd_dir, fname)
            if not os.path.isfile(fpath):
                continue

            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get('players'), list):
                    continue

                for p in data['players']:
                    if not isinstance(p, dict):
                        continue
                    sid = str(p.get('steamid') or '')
                    if sid.startswith('7656'):
                        sid = convert_steamid64_to_steamid3(sid)
                    if not sid:
                        continue

                    proofs = p.get('proof', [])

                    if sid in all_data:
                        existing = all_data[sid]
                        if p.get('last_seen', {}).get('time', 0) > existing.get('last_seen', {}).get('time', 0):
                            existing['last_seen'] = p['last_seen']

                        existing['attributes'] = list(set(
                            existing.get('attributes', []) + p.get('attributes', [])
                        ))
                        existing.setdefault('sources', []).append(fname)

                        if proofs:
                            existing.setdefault('proof_sources', {})[fname] = proofs
                    else:
                        all_data[sid] = {k: v for k, v in p.items() if k != 'steamid'}
                        all_data[sid]['sources'] = [fname]
                        if proofs:
                            all_data[sid]['proof_sources'] = {fname: proofs}

            except Exception as e:
                errors.append(f"{fname}: {e}")

        err_msg = None
        if errors:
            err_msg = "Failed to load some lists:\n" + "\n".join(errors[:5])
        return all_data, err_msg

    def update_tf2bd_lists(self, respect_auto_update=True):
        """Refresh list files from their configured source URLs.

        A list must be Enabled and have its per-list update flag selected before
        startup or manual bulk updates will touch it.
        """
        messages = []
        for entry in [dict(item) for item in self.lists_config]:
            if not entry.get('enabled', True):
                continue
            if respect_auto_update and not entry.get('auto_update', True):
                continue
            if not entry.get('url'):
                continue

            filename = entry.get('filename')
            if not filename:
                continue
            fpath = os.path.join(self.tf2bd_dir, filename)
            if not os.path.isfile(fpath):
                continue

            msg = self._update_json_file(entry)
            if msg:
                messages.append(msg)
        return messages

    def _update_json_file(self, entry):
        filename = entry.get('filename', '')
        url = entry.get('url', '')
        fpath = os.path.join(self.tf2bd_dir, filename)

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            new_data, effective_url = self._prepare_downloaded_data(
                resp.json(), url, filename
            )

            # Normalize the existing file's update_url before comparing so an
            # upstream endpoint migration is treated as metadata, not a player
            # data change.
            metadata_url_changed = False
            if isinstance(data, dict):
                info = data.get('file_info')
                if not isinstance(info, dict):
                    info = {}
                    data['file_info'] = info
                previous_file_url = str(info.get('update_url') or '').strip()
                metadata_url_changed = previous_file_url != effective_url
                info['update_url'] = effective_url

            i = self._find_list_index(filename)
            if i >= 0 and effective_url != url:
                self.lists_config[i]['url'] = effective_url

            old_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            new_hash = hashlib.sha256(json.dumps(new_data, sort_keys=True).encode()).hexdigest()

            if old_hash != new_hash:
                atomic_write_bytes(
                    fpath,
                    json.dumps(new_data, indent=2).encode('utf-8'),
                )
                self._mark_runtime_file_changed(filename)
                n_players = len(new_data['players'])
                self._record_list_result(
                    filename, True,
                    f"Updated ({n_players} players)", n_players,
                )
                return f"Updated {filename}"

            if metadata_url_changed:
                # Keep the local file's embedded update_url in sync with the
                # adopted source without treating metadata-only changes as new
                # player data that requires a restart.
                atomic_write_bytes(
                    fpath,
                    json.dumps(data, indent=2).encode('utf-8'),
                )

            n_players = len(data.get('players', [])) if isinstance(data.get('players'), list) else 0
            self._record_list_result(
                filename, True, "Already up to date", n_players,
            )
            return f"{filename}: already up to date"

        except Exception as e:
            msg = f"Error updating {filename}: {e}"
            self._record_list_result(filename, False, msg, None)
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
