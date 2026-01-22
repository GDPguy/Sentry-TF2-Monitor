import threading
import time
from valve.rcon import RCON, RCONAuthenticationError, RCONTimeoutError

class RConManager:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self.rcon = None
        self.address = ("127.0.0.1", 27015)
        self.lock = threading.Lock()
        self.block_reason = None
        self._timeout_streak = 0

    def _get_creds(self):
        port = self.cfg.get_int("RCon_Port")
        pw = self.cfg.get("RCon_Password")
        if not (1 <= port <= 65535):
            port = 27015
        return port, pw

    def _connect(self, port: int, pw: str) -> bool:
        if self.rcon:
            return True
        if self.block_reason:
            return False
        try:
            self.address = ("127.0.0.1", port)
            self.rcon = RCON(self.address, pw, timeout=20)
            self.rcon.connect()
            self.rcon.authenticate()
            print("RCON connected.")
            self.block_reason = None
            return True
        except RCONAuthenticationError as e:
            err = str(e).lower()
            if "banned" in err:
                print("RCON Banned.")
                self.block_reason = "banned"
            elif "wrong password" in err:
                self.block_reason = "auth_failed"
            else:
                self.block_reason = None
            self._close()
            return False
        except Exception as e:
            print(f"RCON Connection Error: {e}")
            self._close()
            return False

    def _close(self) -> None:
        """
        Close RCON connection.
        MUST be called with self.lock held.
        """
        if self.rcon:
            try:
                self.rcon.close()
            except Exception:
                pass
            self.rcon = None

    def execute(self, command: str):
        port, pw = self._get_creds()

        with self.lock:
            if self.block_reason:
                return False, ""

            if not self.rcon:
                if not self._connect(port, pw):
                    return False, ""

            try:
                response = self.rcon.execute(command.encode("utf-8"))
                self._timeout_streak = 0
                return True, response.body.decode("utf-8", errors="replace")

            except RCONTimeoutError:
                self._timeout_streak += 1
                print(f"RCON timeout")
                if self._timeout_streak >= 2:
                    self._close()
                    self._timeout_streak = 0
                return False, "__TIMEOUT__"
            except Exception as e:
                print(f"RCON error: {type(e).__name__} {e!r}")
                self._close()
                return False, ""

    def reset(self):
        with self.lock:
            self.block_reason = None
            self._close()
