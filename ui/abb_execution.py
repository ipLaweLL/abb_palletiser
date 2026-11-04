"""Non-blocking ABB placement controls and persistent on-screen error log.

The worker only performs socket I/O. All planner/executor/UI state is
updated from Qt's GUI thread after the worker finishes.
"""
from datetime import datetime

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtWidgets import (
    QDockWidget, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from robot.abb_client import ABBClient


class PlaceWorker(QThread):
    """Perform exactly one PLACE request, with no automatic retry."""

    def __init__(self, client, slot, parent=None):
        super().__init__(parent)
        # Snapshot the configured endpoint so tab edits cannot change
        # the destination midway through an in-flight command.
        self.client = ABBClient(
            host=client.host,
            port=client.port,
            timeout_s=client.timeout_s,
            local_ip=client.local_ip,
        )
        self.slot_id = slot.id
        self.x, self.y, self.z = slot.x, slot.y, slot.z
        self.reply = None
        self.error = None

    def run(self):
        try:
            self.reply = self.client.place(
                slot_id=self.slot_id, x=self.x, y=self.y, z=self.z
            )
        except OSError as exc:
            self.error = ("TCP/IP", f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            self.error = ("Python", f"{type(exc).__name__}: {exc}")


class AbbExecutionMixin:
    """Shared ABB UI workflow used by both independent GUI classes."""

    def init_abb_execution(self):
        self._abb_worker = None
        self._place_all_running = False
        self._place_all_stop_requested = False
        self._abb_uncertain = False

        self.error_dock = QDockWidget("Communication & Error Log", self)
        self.error_dock.setObjectName("abbErrorLogDock")
        self.error_dock.setAllowedAreas(
            Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea
        )
        pane = QWidget()
        pane_layout = QVBoxLayout(pane)
        self.error_log = QPlainTextEdit()
        self.error_log.setReadOnly(True)
        self.error_log.setPlaceholderText(
            "Connection failures, ABB replies, and application errors appear here."
        )
        pane_layout.addWidget(self.error_log)
        row = QHBoxLayout()
        show_help = QLabel("Log source: Python / TCP/IP / ABB / Planner")
        row.addWidget(show_help)
        row.addStretch()
        clear = QPushButton("Clear Log")
        clear.clicked.connect(self.error_log.clear)
        row.addWidget(clear)
        pane_layout.addLayout(row)
        self.error_dock.setWidget(pane)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.error_dock)

    def log_error(self, source, message, slot=None):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        where = f" | Slot {slot}" if slot is not None else ""
        self.error_log.appendPlainText(
            f"[{stamp}] [{source}]{where} {message}"
        )
        self.error_dock.show()

    def _set_abb_buttons(self):
        busy = self._abb_worker is not None
        remaining = bool(self.slots) and not self.executor.is_complete()
        simulation_running = (
            hasattr(self, "auto_sim_timer")
            and self.auto_sim_timer.isActive()
        )
        can_place = remaining and not busy and not simulation_running and not self._abb_uncertain
        self.simulate_button.setEnabled(can_place and not self._place_all_running)
        self.place_all_button.setEnabled(
            remaining and not simulation_running and (
                self._place_all_running or can_place
            )
        )
        self.place_all_button.setText(
            "Stop After Current" if self._place_all_running else "Place All with ABB"
        )
        if self._place_all_running and self._place_all_stop_requested:
            self.place_all_button.setEnabled(False)
        if hasattr(self, "local_sim_button"):
            self.local_sim_button.setEnabled(
                remaining and not busy and not self._place_all_running
                and not simulation_running and not self._abb_uncertain
            )
        if hasattr(self, "simulate_all_button"):
            self.simulate_all_button.setEnabled(
                remaining and not busy and not self._place_all_running
                and not self._abb_uncertain
            )
        self.generate_button.setEnabled(not busy and not self._place_all_running)
        self.reset_button.setEnabled(not busy and not self._place_all_running)

    def _start_abb_place(self):
        if self._abb_worker is not None or self._abb_uncertain:
            return
        slot = self.executor.current_slot()
        if slot is None:
            self._finish_place_all()
            return
        self._abb_worker = PlaceWorker(self.abb, slot, self)
        self._abb_worker.finished.connect(self._on_abb_place_finished)
        self.status_label.setText(
            f"Status: Waiting for ABB confirmation of slot {slot.id}"
        )
        self._set_abb_buttons()
        self._abb_worker.start()

    def simulate_place(self):
        """Existing 'Place Next with ABB' action, now non-blocking."""
        if self._place_all_running:
            return
        self._start_abb_place()

    def toggle_place_all(self):
        if self._place_all_running:
            self._place_all_stop_requested = True
            self.status_label.setText(
                "Status: Stop requested — waiting for current ABB reply"
            )
            self._set_abb_buttons()
            return
        if self._abb_worker is not None or self._abb_uncertain:
            return
        if not self.slots or self.executor.is_complete():
            return
        self._place_all_running = True
        self._place_all_stop_requested = False
        if hasattr(self, "_stop_auto_sim"):
            self._stop_auto_sim()
        self._start_abb_place()

    def _on_abb_place_finished(self):
        worker = self._abb_worker
        if worker is None:
            return
        self._abb_worker = None
        worker.deleteLater()

        slot = self.executor.current_slot()
        if slot is None or slot.id != worker.slot_id:
            self.log_error(
                "Python",
                "Current slot changed during ABB request; execution halted.",
                worker.slot_id,
            )
            self._abb_uncertain = True
            self._finish_place_all()
            return

        if worker.error is not None:
            source, detail = worker.error
            self.log_error(
                source,
                f"{detail} | ABB endpoint {worker.client.host}:{worker.client.port}. "
                "Movement completion is UNKNOWN; verify on controller before resuming.",
                worker.slot_id,
            )
            self._abb_uncertain = True
            self.status_label.setText("Status: ABB connection error — check log")
            self._finish_place_all()
            return

        if worker.reply != "PLACED":
            self.log_error(
                "ABB",
                f"Unconfirmed response: {worker.reply!r}. "
                "Placement is NOT marked done. Check RAPID/RobotStudio.",
                worker.slot_id,
            )
            self._abb_uncertain = True
            self.status_label.setText("Status: ABB placement not confirmed — check log")
            self._finish_place_all()
            return

        # Mutate the executor ONLY on the GUI thread after exact ACK.
        slot.status = "DONE"
        self.executor.current_index += 1
        self.executor._mark_next_active()
        self.update_status()
        self._refresh_views()

        if self.executor.is_complete():
            self.status_label.setText("Status: PALLET COMPLETE")
            self._finish_place_all()
        elif self._place_all_running and not self._place_all_stop_requested:
            self.status_label.setText(
                f"Status: ABB confirmed slot {worker.slot_id}; continuing"
            )
            # Schedule the next command after GUI has processed the update.
            QTimer.singleShot(0, self._continue_place_all)
        else:
            self.status_label.setText(
                f"Status: ABB confirmed slot {worker.slot_id}"
            )
            self._finish_place_all()

    def _continue_place_all(self):
        if self._place_all_running and not self._place_all_stop_requested:
            self._start_abb_place()
        else:
            self._finish_place_all()

    def _finish_place_all(self):
        self._place_all_running = False
        self._place_all_stop_requested = False
        self._set_abb_buttons()

    def _guard_abb_operation(self):
        """Prevent loading/resetting a plan while ABB may be moving."""
        if self._abb_worker is not None or self._place_all_running:
            self.log_error(
                "Python",
                "Cannot change plan while an ABB command is in progress. "
                "Request Stop After Current and await acknowledgement.",
            )
            return False
        return True

    def _clear_abb_uncertainty_on_reset(self):
        # Reset is an explicit operator action, never an automatic retry.
        if self._abb_uncertain:
            self.log_error(
                "Python",
                "Operator reset requested after uncertain ABB state. "
                "Verify physical/RobotStudio pallet first; reset may not reflect reality.",
            )
        self._abb_uncertain = False
