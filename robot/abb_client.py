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
        local_ip: str = "",
    ):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        # Empty means OS chooses the outbound source interface.
        self.local_ip = local_ip

    def place(
        self,
        slot_id: int,
        x: float,
        y: float,
        z: float,
        on_event=None,
    ) -> str:
        message = build_place_message(slot_id, x, y, z)

        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        ) as sock:
            sock.settimeout(self.timeout_s)
            if self.local_ip:
                sock.bind((self.local_ip, 0))
            sock.connect((self.host, self.port))

            sock.sendall(message.encode("ascii"))
            print("ABB SEND:", message)
            if on_event is not None:
                on_event("ABB SEND", message)

            # Connection establishment still has a timeout, but a physical
            # pick/place cycle can take arbitrarily long. Wait for RAPID's
            # completion acknowledgement without a receive deadline.
            # The GUI worker is asynchronous; it updates the pallet only
            # when the exact PLACED reply arrives.
            sock.settimeout(None)
            if on_event is not None:
                on_event("ABB", "Waiting for PLACED acknowledgement (no placement timeout)")

            reply = sock.recv(1024).decode(
                "ascii",
                errors="replace",
            ).strip()

            print("ABB REPLY:", reply)
            if on_event is not None:
                on_event("ABB REPLY", reply)
            return reply