import configparser
import os
import threading
import time
import io
import re
from .consts import DEFAULT_SETTINGS
from .utils import atomic_write_bytes

class ConfigManager:
    def __init__(self, cfg_dir='cfg'):
        self.lock = threading.RLock()
        self.cfg_directory = cfg_dir
        self.settings_path = os.path.join(self.cfg_directory, 'settings.ini')
        self.config = configparser.ConfigParser()
        self.error_msg = None
        self._ensure_dir()
        self.load_settings()

    def _ensure_dir(self):
        os.makedirs(self.cfg_directory, exist_ok=True)

    def load_settings(self):
        with self.lock:
            try:
                dataset = self.config.read(self.settings_path)
                if os.path.exists(self.settings_path):
                    if not dataset: raise configparser.Error("Empty/Unparseable")
                    if 'Settings' not in self.config: raise configparser.Error("Missing [Settings]")
                else:
                    self.init_config()
            except configparser.Error as e:
                self._handle_corruption(e)

    def _handle_corruption(self, e):
        timestamp = int(time.time())
        backup_path = self.settings_path + f".{timestamp}.corrupt"
        try:
            os.rename(self.settings_path, backup_path)
            self.error_msg = f"Settings corrupted ({e}). Backed up to {os.path.basename(backup_path)}."
        except OSError:
            self.error_msg = f"Settings corrupted ({e}). Could not backup the file."
        self.config = configparser.ConfigParser()
        self.init_config()

    def init_config(self):
        with self.lock:
            self.config['Settings'] = DEFAULT_SETTINGS
            self.save_settings()

    def save_settings(self):
        with self.lock:
            try:
                buf = io.StringIO()
                self.config.write(buf)
                atomic_write_bytes(self.settings_path, buf.getvalue().encode("utf-8"))
            except Exception as e:
                print(f"Error saving settings: {e}")

    def get(self, key):
        with self.lock:
            return self.config.get('Settings', key, fallback=DEFAULT_SETTINGS.get(key, ""))

    def get_int(self, key):
        with self.lock:
            val = self.get(key)
            try: return int(float(val))
            except ValueError: return int(float(DEFAULT_SETTINGS.get(key, "0")))

    def get_bool(self, key):
        with self.lock:
            val = self.get(key)
            return val.lower() in ('true', '1', 'yes', 'on')

    def get_float(self, key):
        with self.lock:
            val = self.get(key)
            try: return float(val)
            except ValueError: return 0.0

    def get_color(self, key):
        with self.lock:
            val = self.get(key)
            if re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', val):
                return val
            return DEFAULT_SETTINGS.get(key, "#ffffff")

    def set(self, key, value):
        with self.lock:
            if 'Settings' not in self.config: self.config['Settings'] = {}
            self.config['Settings'][key] = str(value)
            self.save_settings()
