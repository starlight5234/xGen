"""
xGen Global Crash & Exception Dialog.
Catches unhandled exceptions, prevents silent UI crashes, and provides 1-click diagnostic copy.
"""

from __future__ import annotations

import logging
import sys
import traceback
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("xgen.crash")


class CrashDialog(QDialog):
    """Clean diagnostic dialog presented when an unexpected exception occurs."""

    def __init__(self, exc_type, exc_value, exc_tb, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("xGen — Unexpected Error")
        self.resize(650, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(
            "QDialog { background: #181a1f; color: #d0d7de; }"
            "QLabel { color: #e0e0e0; }"
            "QTextEdit { background: #121417; color: #ff8a80; border: 1px solid #3c4048; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 11px; padding: 6px; }"
            "QPushButton { background: #2b303c; color: #ffffff; border: 1px solid #3c4454; border-radius: 4px; padding: 6px 14px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background: #383f4f; }"
        )

        formatted_tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self.report_text = f"xGen Crash Diagnostic Report\n{'='*35}\nException: {exc_type.__name__}: {exc_value}\n\nTraceback:\n{formatted_tb}"

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with warning badge
        lbl_header = QLabel("⚠️ An unexpected error occurred in xGen")
        lbl_header.setStyleSheet("color: #ff5252; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl_header)

        lbl_desc = QLabel("The details below have been saved to your log file. You can copy this report to share with the team:")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(lbl_desc)

        # Text area with traceback
        self.txt_trace = QTextEdit()
        self.txt_trace.setPlainText(self.report_text)
        self.txt_trace.setReadOnly(True)
        layout.addWidget(self.txt_trace)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_copy = QPushButton("📋 Copy Crash Report")
        self.btn_copy.clicked.connect(self._on_copy)
        btn_layout.addWidget(self.btn_copy)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _on_copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.report_text)
        self.btn_copy.setText("Copied ✓")
        self.btn_copy.setStyleSheet("QPushButton { background: #2e7d32; color: #ffffff; border-radius: 4px; padding: 6px 14px; font-weight: bold; font-size: 11px; }")


def install_global_excepthook() -> None:
    """Installs sys.excepthook handler to prevent silent crashes."""
    def _handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        logger.critical("Unhandled exception caught by global boundary:", exc_info=(exc_type, exc_value, exc_tb))

        app = QApplication.instance()
        if app:
            try:
                dialog = CrashDialog(exc_type, exc_value, exc_tb)
                dialog.exec()
            except Exception as e:
                logger.critical("Could not display crash dialog: %s", e)

    sys.excepthook = _handle_exception
