"""Read ABB controller event messages using Robot Web Services (RWS).

This is separate from the RAPID PLACE/PLACED TCP socket protocol.
Supports RobotWare 6 RWS-style XHTML and Digest/Basic authentication.
"""
import http.cookiejar
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from PySide6.QtCore import QThread, Signal


def parse_event_log(xml_bytes):
    """Extract structured entries from ABB's /rw/elog/0?lang=en XHTML."""
    root = ET.fromstring(xml_bytes)
    events = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "li":
            continue
        css_class = element.attrib.get("class", "")
        if "elog-message" not in css_class:
            continue
        values = {}
        for child in element.iter():
            if child is element:
                continue
            name = child.attrib.get("class", "").strip()
            if name:
                values[name] = " ".join("".join(child.itertext()).split())
        resource = element.attrib.get("title", "")
        sequence = resource.rsplit("/", 1)[-1]
        code = values.get("code", "?")
        timestamp = values.get("tstamp", "")
        severity = values.get("msgtype", values.get("msg-type", ""))
        title = values.get("title", "")
        description = values.get("desc", "")
        source = values.get("src-name", "Controller")
        arguments = [
            val for key, val in sorted(values.items())
            if key.startswith("arg") and key != "argc"
        ]
        events.append({
            "key": (sequence, code, timestamp),
            "seq": sequence,
            "code": code,
            "time": timestamp,
            "severity": severity,
            "source": source,
            "title": title,
            "description": description,
            "arguments": arguments,
        })
    return events


def _event_message(entry):
    severity = {"1": "INFO", "2": "WARNING", "3": "ERROR"}.get(
        entry["severity"], "EVENT"
    )
    detail = entry["title"] or entry["description"] or "Controller event"
    args = " | ".join(entry["arguments"])
    return (
        f"{severity} {entry['code']} — {detail}"
        f" | Source: {entry['source']}"
        f"{(' | ' + args) if args else ''}"
        f"{(' | Controller time: ' + entry['time']) if entry['time'] else ''}"
    )


class RwsEventWorker(QThread):
    event_received = Signal(str, bool)
    connection_status = Signal(str)

    def __init__(self, base_url, username, password, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        parts = urlsplit(self.base_url)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            self.connection_status.emit(
                "Invalid RWS URL. Use http://host:port or https://host:port."
            )
            return

        # Authentication is required by ABB RWS. Do not store credentials.
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(
            None, self.base_url + "/", self.username, self.password
        )
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPDigestAuthHandler(password_mgr),
            urllib.request.HTTPBasicAuthHandler(password_mgr),
        )
        url = self.base_url + "/rw/elog/0?lang=en&order=lifo"
        seen = set()
        last_failure = None
        connected = False

        while not self._stop_event.is_set():
            try:
                request = urllib.request.Request(
                    url, headers={"Accept": "application/xhtml+xml"}
                )
                with opener.open(request, timeout=4.0) as response:
                    entries = parse_event_log(response.read(2_000_000))
                if not connected:
                    self.connection_status.emit("Connected to ABB event log")
                    connected = True
                last_failure = None
                # First read includes the most recent 30 controller events,
                # including errors already visible in RobotStudio.
                if not seen:
                    selected = list(reversed(entries[:30]))
                else:
                    selected = [
                        entry for entry in reversed(entries)
                        if entry["key"] not in seen
                    ]
                for entry in selected:
                    key = entry["key"]
                    if key not in seen:
                        seen.add(key)
                        self.event_received.emit(
                            _event_message(entry), entry["severity"] == "3"
                        )
                for entry in entries:
                    seen.add(entry["key"])
            except (urllib.error.URLError, OSError, ValueError, ET.ParseError) as error:
                description = f"{type(error).__name__}: {error}"
                if description != last_failure:
                    self.connection_status.emit(
                        f"ABB event log unavailable: {description}"
                    )
                    last_failure = description
                connected = False
            except Exception as error:
                # Unanticipated parser/API changes must be visible, not silent.
                self.connection_status.emit(
                    f"ABB RWS reader failure: {type(error).__name__}: {error}"
                )
                return
            self._stop_event.wait(2.0)
