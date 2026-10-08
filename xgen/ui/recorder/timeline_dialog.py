"""
Recorder Timeline Dialog.
Clean modal/modeless window housing the RecorderPanel timeline and details.
"""
from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QWidget

from xgen.recorder.api import RecorderApi
from xgen.ui.recorder.bridge import RecorderQtBridge
from xgen.ui.recorder.panel import RecorderPanel


class RecorderTimelineDialog(QDialog):
    """
    Dedicated dialog window displaying the recorded steps timeline and details.
    """
    def __init__(self, api: RecorderApi, bridge: RecorderQtBridge, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.api = api
        self.bridge = bridge

        self.setWindowTitle("xGen — Recorder Timeline")
        self.resize(1000, 620)
        self.setMinimumSize(780, 480)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = RecorderPanel(self.api, self.bridge, self)
        layout.addWidget(self.panel)

        self.setStyleSheet("""
            QDialog {
                background: #0f172a;
            }
        """)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Always refresh latest timeline when opening dialog
        self.panel.refresh_timeline()
