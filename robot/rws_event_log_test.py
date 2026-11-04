"""Offline regression test for ABB RWS XHTML event parsing.

Run: python -m robot.rws_event_log_test
"""
from robot.rws_event_log import parse_event_log, _event_message


def main():
    example = b'''<?xml version="1.0" encoding="utf-8"?>
    <html xmlns="http://www.w3.org/1999/xhtml">
      <body><div class="state"><ul>
        <li class="elog-message-li" title="/rw/elog/0/42">
          <span class="msgtype">3</span>
          <span class="code">50050</span>
          <span class="src-name">T_ROB1</span>
          <span class="tstamp">2026-11-04 T 12:10:00</span>
          <span class="title">Position outside reach</span>
        </li>
      </ul></div></body>
    </html>'''
    entries = parse_event_log(example)
    assert len(entries) == 1, entries
    e = entries[0]
    assert e["code"] == "50050", e
    assert e["severity"] == "3", e
    assert e["source"] == "T_ROB1", e
    assert "Position outside reach" in _event_message(e), e
    print("PASS ABB RWS event parsing: code, source, title, severity")


if __name__ == "__main__":
    main()
