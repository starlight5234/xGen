"""
Floating Recorder Overlay Widget.
Active, draggable, always-on-top pill that appears when recording starts,
allowing seamless pause/resume/stop while xGen is minimized out of the way.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
)

logger = logging.getLogger("xgen.ui.recorder.overlay")


class FloatingRecorderOverlay(QWidget):
    """
    Compact floating pill widget that stays on top of all windows during recording.
    """
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._is_paused = False
        self._elapsed_seconds = 0
        self._step_count = 0
        self._drag_pos: Optional[QPoint] = None

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(48)
        self.setMinimumWidth(340)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Container with dark glassmorphism styling
        self.container = QFrame(self)
        self.container.setStyleSheet("""
            QFrame {
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid rgba(239, 68, 68, 0.6);
                border-radius: 24px;
            }
        """)
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(16, 6, 16, 6)
        container_layout.setSpacing(10)

        # Drag Grip Handle
        self.lbl_grip = QLabel("⠿", self.container)
        self.lbl_grip.setStyleSheet("color: #64748b; font-size: 16px; font-weight: bold; background: transparent; border: none;")
        self.lbl_grip.setToolTip("Click and drag to move overlay")
        self.lbl_grip.setCursor(Qt.CursorShape.SizeAllCursor)
        container_layout.addWidget(self.lbl_grip)

        # Pulsing Red Dot & Timer
        self.lbl_timer = QLabel("● REC  00:00", self.container)
        self.lbl_timer.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_timer.setStyleSheet("color: #f87171; background: transparent; border: none;")
        container_layout.addWidget(self.lbl_timer)

        # Step count pill badge
        self.lbl_steps = QLabel("0 steps", self.container)
        self.lbl_steps.setStyleSheet("""
            background: #1e293b;
            color: #94a3b8;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: 600;
        """)
        container_layout.addWidget(self.lbl_steps)

        # Divider
        divider = QFrame(self.container)
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("background: #334155; max-width: 1px;")
        container_layout.addWidget(divider)

        # Pause / Resume Button
        self.btn_pause = QPushButton("⏸ Pause", self.container)
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 12px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #334155;
                border-color: #94a3b8;
            }
        """)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        container_layout.addWidget(self.btn_pause)

        # Stop Button
        self.btn_stop = QPushButton("⏹ Stop", self.container)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: #ffffff;
                border: 1px solid #ef4444;
                border-radius: 12px;
                padding: 4px 14px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #b91c1c;
                border-color: #f87171;
            }
        """)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        container_layout.addWidget(self.btn_stop)

        main_layout.addWidget(self.container)

    # -------------------------------------------------------------------------
    # Dragging Support
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # -------------------------------------------------------------------------
    # State and Actions
    # -------------------------------------------------------------------------

    def _on_tick(self) -> None:
        if not self._is_paused:
            self._elapsed_seconds += 1
            mins = self._elapsed_seconds // 60
            secs = self._elapsed_seconds % 60
            self.lbl_timer.setText(f"● REC  {mins:02d}:{secs:02d}")

    def _on_pause_clicked(self) -> None:
        if self._is_paused:
            self.resume_requested.emit()
        else:
            self.pause_requested.emit()

    def set_paused(self, is_paused: bool) -> None:
        self._is_paused = is_paused
        if is_paused:
            mins = self._elapsed_seconds // 60
            secs = self._elapsed_seconds % 60
            self.lbl_timer.setText(f"⏸ PAUSED  {mins:02d}:{secs:02d}")
            self.lbl_timer.setStyleSheet("color: #fbbf24; background: transparent; border: none;")
            self.btn_pause.setText("▶ Resume")
            self.container.setStyleSheet("""
                QFrame {
                    background: rgba(15, 23, 42, 0.95);
                    border: 1px solid rgba(251, 191, 36, 0.7);
                    border-radius: 24px;
                }
            """)
        else:
            mins = self._elapsed_seconds // 60
            secs = self._elapsed_seconds % 60
            self.lbl_timer.setText(f"● REC  {mins:02d}:{secs:02d}")
            self.lbl_timer.setStyleSheet("color: #f87171; background: transparent; border: none;")
            self.btn_pause.setText("⏸ Pause")
            self.container.setStyleSheet("""
                QFrame {
                    background: rgba(15, 23, 42, 0.95);
                    border: 1px solid rgba(239, 68, 68, 0.7);
                    border-radius: 24px;
                }
            """)

    def set_step_count(self, count: int) -> None:
        self._step_count = count
        self.lbl_steps.setText(f"{count} step{'s' if count != 1 else ''}")

    def show_overlay(self) -> None:
        """Position at top-center of primary screen and show."""
        self._elapsed_seconds = 0
        self._step_count = 0
        self.set_paused(False)
        self.lbl_steps.setText("0 steps")
        self._timer.start()

        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + 24
            self.move(x, y)

        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()
