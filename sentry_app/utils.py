import os
import tempfile

def atomic_write_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.basename(path)
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=base + ".", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    finally:
        if fd is not None:
            try: os.close(fd)
            except Exception: pass
        if tmp_path is not None and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass

def convert_steamid64_to_steamid3(steamid64):
    try:
        steamid64 = int(steamid64)
        steamid3 = "[U:1:" + str(steamid64 - 76561197960265728) + "]"
        return steamid3
    except Exception:
        return None

def convert_steamid3_to_steamid64(steamid3):
    if not steamid3: return None
    parts = steamid3.split(':')
    if len(parts) == 3:
        try:
            steamid_num = int(parts[2].rstrip(']'))
            steamid64 = steamid_num + 76561197960265728
            return steamid64
        except ValueError:
            return None
    return None
