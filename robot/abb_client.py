import socket

from robot.protocol import build_place_message

# ============================================================
# ABB TCP CLIENT
# ============================================================

ABB_HOST = "127.0.0.1"
ABB_PORT = 5000
ABB_TIMEOUT_S = 60.0


class ABBClient:
    """Small adapter for the RAPID protocol:
    PLACE;<slot_id>;<x>;<y>;<z>  ->  PLACED
    """

    def __init__(
        self,
        host: str = ABB_HOST,
        port: int = ABB_PORT,
        timeout_s: float = ABB_TIMEOUT_S,
    ):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s

    def place(
        self,
        slot_id: int,
        x: float,
        y: float,
        z: float,
    ) -> str:
        message = (
            f"PLACE;"
            f"{int(slot_id)};"
            f"{x:.3f};"
            f"{y:.3f};"
            f"{z:.3f}"
        )

        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        ) as sock:
            sock.settimeout(self.timeout_s)
            sock.connect((self.host, self.port))

            print("ABB SEND:", message)
            sock.sendall(message.encode("ascii"))

            reply = sock.recv(1024).decode(
                "ascii",
                errors="replace",
            ).strip()

            print("ABB REPLY:", reply)
            return reply