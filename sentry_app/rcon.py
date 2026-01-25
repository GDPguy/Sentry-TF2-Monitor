import socket
import struct
import threading

SERVERDATA_RESPONSE_VALUE = 0
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2

ID_AUTH = 999
ID_COMMAND_REAL = 100
ID_COMMAND_MARKER = 101

def pack_rcon_packet(req_id: int, cmd_type: int, body: str) -> bytes:
    body_bytes = body.encode("utf-8")
    packet_size = 10 + len(body_bytes)
    fmt = f"<iii{len(body_bytes)}sxx"
    return struct.pack(fmt, packet_size, req_id, cmd_type, body_bytes)

def read_rcon_packet(sock: socket.socket):
    size_bytes = b""
    while len(size_bytes) < 4:
        chunk = sock.recv(4 - len(size_bytes))
        if not chunk: return None
        size_bytes += chunk

    packet_size = struct.unpack("<i", size_bytes)[0]

    payload = b""
    while len(payload) < packet_size:
        chunk = sock.recv(packet_size - len(payload))
        if not chunk: return None
        payload += chunk

    req_id, pkt_type = struct.unpack("<ii", payload[:8])
    body = payload[8:-2]
    return req_id, pkt_type, body

class RconConnection:
    def __init__(self, host: str, port: int, password: str, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.sock = None

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.authenticate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sock:
            try: self.sock.close()
            except: pass

    def authenticate(self):
        self.sock.sendall(pack_rcon_packet(ID_AUTH, SERVERDATA_AUTH, self.password))

        while True:
            pkt = read_rcon_packet(self.sock)
            if pkt is None:
                raise ConnectionError("RCON authentication failed: Socket closed during handshake")

            req_id, pkt_type, _ = pkt

            if pkt_type == SERVERDATA_AUTH_RESPONSE:
                if req_id == -1:
                    raise PermissionError("RCON authentication failed: Wrong password")
                if req_id == ID_AUTH:
                    return

class RConManager:
    def __init__(self, config_manager):
        self.cfg = config_manager
        self.lock = threading.Lock()
        self.block_reason = None

    def _get_creds(self):
        port = self.cfg.get_int("RCon_Port")
        pw = self.cfg.get("RCon_Password")
        if not (1 <= port <= 65535):
            port = 27015
        return port, pw

    def execute(self, command: str) -> tuple[bool, str]:
        port, pw = self._get_creds()

        with self.lock:
            if self.block_reason:
                return False, ""

            try:
                with RconConnection("127.0.0.1", port, pw) as conn:

                    conn.sock.sendall(pack_rcon_packet(ID_COMMAND_REAL, SERVERDATA_EXECCOMMAND, command))
                    conn.sock.sendall(pack_rcon_packet(ID_COMMAND_MARKER, SERVERDATA_EXECCOMMAND, ""))

                    response_buffer = []
                    while True:
                        pkt = read_rcon_packet(conn.sock)
                        if pkt is None: break

                        req_id, _, body = pkt

                        if req_id == ID_COMMAND_REAL:
                            response_buffer.append(body)
                        elif req_id == ID_COMMAND_MARKER:
                            break

                    full_body = b"".join(response_buffer)
                    text = full_body.decode("utf-8", errors="replace")

                    return True, text

            except (socket.timeout, TimeoutError):
                return False, "__TIMEOUT__"
            except PermissionError:
                print("RCON Error: Wrong Password")
                self.block_reason = "auth_failed"
                return False, ""
            except ConnectionResetError:
                print("RCON Error: Connection Reset (Server banned IP?)")
                self.block_reason = "banned"
                return False, ""
            except ConnectionError:
                print("RCON Error: Connection Error")
                return False, ""
            except ConnectionRefusedError:
                return False, ""
            except Exception as e:
                err = str(e).lower()
                print(err)
                if "banned" in err:
                    self.block_reason = "banned"
                return False, ""

    def reset(self):
        with self.lock:
            self.block_reason = None
