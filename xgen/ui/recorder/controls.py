"""
Recorder Toolbar Controls Widget.
Provides Record, Pause, Stop buttons and an active recording status pill
designed to fit into the xGen top toolbar.
"""
from __future__ import annotations

import logging
from typing import Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget
)

logger = logging.getLogger("xgen.ui.recorder.controls")


class RecorderControls(QWidget):
    """
    Toolbar control cluster for controlling recorder sessions and displaying status.
    """
    start_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    toggle_panel_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_state = "idle"
        self._elapsed_seconds = 0
        self._step_count = 0

        # Timer for duration update in UI
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._init_ui()
        self.set_state("idle")

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Record Button
        self.btn_record = QPushButton("🔴 Record", self)
        self.btn_record.setToolTip("Start recording user actions (F9)")
        self.btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_record.clicked.connect(self._on_record_clicked)

        # Pause Button
        self.btn_pause = QPushButton("⏸ Pause", self)
        self.btn_pause.setToolTip("Pause or resume active recording (F10)")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.clicked.connect(self._on_pause_clicked)

        # Stop Button
        self.btn_stop = QPushButton("⏹ Stop", self)
        self.btn_stop.setToolTip("Stop and finalize recording session")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop_requested.emit)

        # Toggle Panel Button
        self.btn_panel = QPushButton("📋 Timeline", self)
        self.btn_panel.setToolTip("Toggle recorder steps timeline panel")
        self.btn_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_panel.clicked.connect(self.toggle_panel_requested.emit)

        # Status Pill Indicator
        self.lbl_status = QLabel("IDLE", self)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout.addWidget(self.btn_record)
        layout.addWidget(self.btn_pause)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_panel)
        layout.addWidget(self.lbl_status)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QPushButton {
                background: #1e222d;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #282f3e;
                border-color: #475569;
            }
            QPushButton:disabled {
                color: #64748b;
                background: #141720;
                border-color: #1e222d;
            }
        """)

    def _on_record_clicked(self) -> None:
        if self._current_state in ("idle", "error"):
            self.start_requested.emit()
        elif self._current_state in ("recording", "paused"):
            self.stop_requested.emit()

    def _on_pause_clicked(self) -> None:
        if self._current_state == "recording":
            self.pause_requested.emit()
        elif self._current_state == "paused":
            self.resume_requested.emit()

    def _on_tick(self) -> None:
        if self._current_state == "recording":
            self._elapsed_seconds += 1
            self._update_status_label()

    def _update_status_label(self) -> None:
        m, s = divmod(self._elapsed_seconds, 60)
        time_str = f"{m:02d}:{s:02d}"

        if self._current_state == "recording":
            self.lbl_status.setText(f"● REC {time_str} ({self._step_count})")
            self.lbl_status.setStyleSheet("""
                background: #450a0a;
                color: #f87171;
                border: 1px solid #ef4444;
                border-radius: 10px;
                padding: 2px 8px;
                font-weight: 600;
                font-size: 11px;
            """)
        elif self._current_state == "paused":
            self.lbl_status.setText(f"⏸ PAUSED ({self._step_count})")
            self.lbl_status.setStyleSheet("""
                background: #451a03;
                color: #fbbf24;
                border: 1px solid #f59e0b;
                border-radius: 10px;
                padding: 2px 8px;
                font-weight: 600;
                font-size: 11px;
            """)
        else:
            self.lbl_status.setText("IDLE")
            self.lbl_status.setStyleSheet("""
                background: #0f172a;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 2px 8px;
                font-weight: 500;
                font-size: 11px;
            """)

    def set_state(self, state_str: str, duration_sec: float = 0.0, step_count: int = 0) -> None:
        """Updates UI control buttons and status badge to match backend state."""
        self._current_state = state_str.lower()
        self._elapsed_seconds = int(duration_sec)
        self._step_count = step_count

        if self._current_state == "recording":
            self.btn_record.setText("⏹ Stop")
            self.btn_record.setStyleSheet("background: #7f1d1d; color: #fecaca; border: 1px solid #ef4444;")
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("⏸ Pause")
            self.btn_stop.setEnabled(True)
            if not self._timer.isActive():
                self._timer.start()

        elif self._current_state == "paused":
            self.btn_record.setText("⏹ Stop")
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("▶ Resume")
            self.btn_stop.setEnabled(True)
            self._timer.stop()

        else:  # idle, error, stopping
            self.btn_record.setText("🔴 Record")
            self.btn_record.setStyleSheet("")
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("⏸ Pause")
            self.btn_stop.setEnabled(False)
            self._timer.stop()

        self._update_status_label()

    def update_step_count(self, count: int) -> None:
        self._step_count = count
        self._update_status_label()
