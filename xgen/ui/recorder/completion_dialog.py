"""
Recording Finalized Completion Dialog.
Appears when a recording session stops, offering instant access to:
- Open folder in Windows Explorer
- Export to Action-XPath JSON
- Review steps in the Recorder Timeline tab
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget
)

from xgen.recorder.models import RecordingMeta
from xgen.recorder.service import RecorderService


class RecordingCompletionDialog(QDialog):
    """
    Modal dialog presented after recording stops, providing immediate file actions.
    """
    def __init__(
        self,
        meta: RecordingMeta,
        storage_dir: Path,
        recorder_service: RecorderService,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.meta = meta
        self.storage_dir = Path(storage_dir) / meta.id
        self.recorder_service = recorder_service
        self.view_timeline_requested = False

        self.setWindowTitle("Recording Finalized")
        self.setMinimumWidth(560)
        self.setStyleSheet("""
            QDialog {
                background: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        # Header Title
        lbl_header = QLabel("✅ Recording Finalized Successfully", self)
        lbl_header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        lbl_header.setStyleSheet("color: #38bdf8; background: transparent; border: none;")
        layout.addWidget(lbl_header)

        # Details Card - specifically scoped by objectName so QLabels do NOT inherit QFrame styling
        card = QFrame(self)
        card.setObjectName("detailsCard")
        card.setStyleSheet("""
            QFrame#detailsCard {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QFrame#detailsCard QLabel {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
                color: #e2e8f0;
                font-size: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        lbl_name = QLabel(f"<b>Session Name:</b> &nbsp;<span style='color: #f8fafc;'>{self.meta.name}</span>", card)
        lbl_stats = QLabel(
            f"<b>Captured Steps:</b> &nbsp;<span style='color: #38bdf8; font-weight: 600;'>{self.meta.step_count}</span> "
            f"&nbsp;&nbsp;&bull;&nbsp;&nbsp; "
            f"<b>Duration:</b> &nbsp;<span style='color: #a78bfa; font-weight: 600;'>{self.meta.duration_seconds:.2f}s</span>",
            card
        )
        card_layout.addWidget(lbl_name)
        card_layout.addWidget(lbl_stats)

        # Path display
        lbl_path_title = QLabel("<b>Saved Location:</b>", card)
        card_layout.addWidget(lbl_path_title)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.txt_path = QLineEdit(str(self.storage_dir), card)
        self.txt_path.setReadOnly(True)
        self.txt_path.setCursorPosition(0)
        self.txt_path.setToolTip(str(self.storage_dir))
        self.txt_path.setStyleSheet("""
            QLineEdit {
                background: #0f172a;
                color: #94a3b8;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
            }
        """)
        path_row.addWidget(self.txt_path)

        self.btn_copy = QPushButton("📋 Copy", card)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: #f1f5f9;
                font-weight: 600;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #475569;
                color: #ffffff;
            }
        """)
        self.btn_copy.clicked.connect(self._copy_path)
        path_row.addWidget(self.btn_copy)

        btn_browse = QPushButton("📂 Open Folder", card)
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setStyleSheet("""
            QPushButton {
                background: #2563eb;
                color: #ffffff;
                font-weight: 600;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
        """)
        btn_browse.clicked.connect(self._open_explorer)
        path_row.addWidget(btn_browse)

        card_layout.addLayout(path_row)
        layout.addWidget(card)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_open_actions = QPushButton("⚡ Open actions.json", self)
        btn_open_actions.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_actions.setToolTip("Open the clean, trimmed Action-XPath automation JSON directly in your editor")
        btn_open_actions.setStyleSheet("""
            QPushButton {
                background: #0d9488;
                color: #ffffff;
                font-weight: 700;
                border: 1px solid #14b8a6;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #0f766e;
                border-color: #2dd4bf;
            }
        """)
        btn_open_actions.clicked.connect(self._open_actions_file)
        btn_row.addWidget(btn_open_actions)

        btn_export = QPushButton("💾 Export As...", self)
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.setStyleSheet("""
            QPushButton {
                background: #059669;
                color: #ffffff;
                font-weight: 600;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #047857;
            }
        """)
        btn_export.clicked.connect(self._export_json)
        btn_row.addWidget(btn_export)

        btn_view_timeline = QPushButton("⏱ View Timeline", self)
        btn_view_timeline.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view_timeline.setToolTip("Open the interactive step timeline inspector")
        btn_view_timeline.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #38bdf8;
                font-weight: 600;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 7px 16px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #0369a1;
                color: #ffffff;
            }
        """)
        btn_view_timeline.clicked.connect(self._on_view_timeline_clicked)
        btn_row.addWidget(btn_view_timeline)

        btn_row.addStretch(1)

        btn_done = QPushButton("Close", self)
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: #f1f5f9;
                font-weight: 600;
                border-radius: 6px;
                padding: 7px 20px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #475569;
            }
        """)
        btn_done.clicked.connect(self.accept)
        btn_row.addWidget(btn_done)

        layout.addLayout(btn_row)

    def _on_view_timeline_clicked(self) -> None:
        self.view_timeline_requested = True
        self.accept()

    def _copy_path(self) -> None:
        """Copy the storage directory path to the system clipboard."""
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        QApplication.clipboard().setText(str(self.storage_dir))
        self.btn_copy.setText("✓ Copied!")
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background: #059669;
                color: #ffffff;
                font-weight: 600;
                border: 1px solid #10b981;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
        """)
        QTimer.singleShot(1500, self._reset_copy_btn)

    def _reset_copy_btn(self) -> None:
        self.btn_copy.setText("📋 Copy")
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background: #334155;
                color: #f1f5f9;
                font-weight: 600;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #475569;
                color: #ffffff;
            }
        """)

    def _open_actions_file(self) -> None:
        """Open the clean trimmed actions.json file directly."""
        actions_path = self.storage_dir / "actions.json"
        if not actions_path.exists():
            # If not yet present, synthesize it on-the-fly
            try:
                res = self.recorder_service.export(self.meta.id, exporter_id="action_xpath_json")
                with open(actions_path, "w", encoding="utf-8") as f:
                    f.write(res.text)
            except Exception as e:
                QMessageBox.critical(self, "Open Failed", f"Could not generate actions.json: {e}")
                return

        if actions_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(actions_path)))
        else:
            QMessageBox.warning(self, "File Not Found", f"actions.json not found in:\n{self.storage_dir}")

    def _open_explorer(self) -> None:
        """Open the target folder in Windows File Explorer."""
        folder_str = str(self.storage_dir)
        if os.path.exists(folder_str):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder_str))
        else:
            QMessageBox.warning(self, "Folder Not Found", f"Directory does not exist yet:\n{folder_str}")

    def _export_json(self) -> None:
        """Export session to an Action-XPath JSON file."""
        default_filename = f"{self.meta.name.strip().replace(' ', '_')}.json"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Action-XPath JSON",
            default_filename,
            "JSON Files (*.json);;All Files (*)"
        )
        if save_path:
            try:
                res = self.recorder_service.export(self.meta.id, exporter_id="action_xpath_json")
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(res.text)
                QMessageBox.information(self, "Export Successful", f"Saved automation JSON to:\n{save_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not export recording: {e}")
