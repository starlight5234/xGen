"""
xGen Status Bar with operational banners and elevation alert buttons.
"""

from __future__ import annotations

import logging
from typing import Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QWidget,
)

from xgen.core.uia_bridge import UIAElement
from xgen.utils.privilege import relaunch_as_admin

logger = logging.getLogger("xgen.status_bar")


class StatusBar(QStatusBar):
    """Bottom status bar with operational status, progress metrics, and action alerts."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet("QStatusBar { background: #0c0e12; color: #94a3b8; font-size: 11px; border-top: 1px solid #1e222b; padding: 2px 4px; }")

        # Main message label
        self.lbl_msg = QLabel("Ready.")
        self.lbl_msg.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: 500;")
        self.addWidget(self.lbl_msg, 1)

        # Progress bar widget
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(140)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #181c24; border: 1px solid #2a3140; border-radius: 5px; }"
            "QProgressBar::chunk { background: #3b82f6; border-radius: 4px; }"
        )
        self.progress_bar.hide()
        self.addPermanentWidget(self.progress_bar)

        # Permanent status pills container
        self.pill_container = QWidget()
        self.pill_layout = QHBoxLayout(self.pill_container)
        self.pill_layout.setContentsMargins(0, 0, 0, 0)
        self.pill_layout.setSpacing(6)

        # Freeze Banner Pill
        self.lbl_freeze = QLabel("🔒 FROZEN")
        self.lbl_freeze.setStyleSheet("background: #e65100; color: #ffffff; padding: 1px 6px; border-radius: 3px; font-weight: bold;")
        self.lbl_freeze.hide()
        self.pill_layout.addWidget(self.lbl_freeze)

        # Large tree warning pill
        self.lbl_large_tree = QLabel("⚠️ Large Tree")
        self.lbl_large_tree.setStyleSheet("background: #f57f17; color: #ffffff; padding: 1px 6px; border-radius: 3px; font-weight: bold;")
        self.lbl_large_tree.hide()
        self.pill_layout.addWidget(self.lbl_large_tree)

        # Admin Elevation Prompt Button
        self.btn_elevation = QPushButton("🔓 Relaunch as Admin")
        self.btn_elevation.setStyleSheet(
            "QPushButton { background: #d32f2f; color: #ffffff; font-weight: bold; padding: 2px 8px; border-radius: 3px; border: none; font-size: 11px; }"
            "QPushButton:hover { background: #f44336; }"
        )
        self.btn_elevation.clicked.connect(relaunch_as_admin)
        self.btn_elevation.hide()
        self.pill_layout.addWidget(self.btn_elevation)

        # Tree age indicator
        self.lbl_age = QLabel("")
        self.lbl_age.setStyleSheet("color: #757575; font-size: 11px;")
        self.pill_layout.addWidget(self.lbl_age)

        self.addPermanentWidget(self.pill_container)

    def show_hover_info(self, el: Optional[UIAElement]) -> None:
        if el is None:
            self.lbl_msg.setText("Hovering: [None]")
            return

        name_part = f'"{el.name}"' if el.name else ""
        id_part = f"[AutomationId={el.automation_id}]" if el.automation_id else ""
        rect_part = f"({el.bounding_rect.width}x{el.bounding_rect.height})" if el.bounding_rect else ""
        self.lbl_msg.setText(f"🎯 Hovering: {el.control_type} {name_part} {id_part} {rect_part}".strip())

    def show_element_selected(self, tag: str, name: str, auto_id: str, age_seconds: int = 0) -> None:
        id_str = f" [AutomationId={auto_id}]" if auto_id else ""
        name_str = f' "{name}"' if name else ""
        self.lbl_msg.setText(f"✅ Selected: {tag}{name_str}{id_str}")
        if age_seconds > 0:
            self.lbl_age.setText(f"Snapshot age: {age_seconds}s")
        else:
            self.lbl_age.setText("")

    def show_progress(self, received_bytes: int, total_bytes: int) -> None:
        self.progress_bar.show()
        if total_bytes > 0:
            self.progress_bar.setMaximum(total_bytes)
            self.progress_bar.setValue(received_bytes)
            kb = received_bytes / 1024.0
            self.lbl_msg.setText(f"Fetching UI tree... ({kb:.1f} KB)")
        else:
            self.progress_bar.setMaximum(0)
            self.progress_bar.setValue(0)
            self.lbl_msg.setText("Fetching UI tree from driver...")

    def hide_progress(self) -> None:
        self.progress_bar.hide()

    def show_freeze_state(self, is_frozen: bool) -> None:
        if is_frozen:
            self.lbl_freeze.show()
            self.lbl_msg.setText("🔒 UI Tree snapshot is locked. Tree refresh paused.")
        else:
            self.lbl_freeze.hide()

    def show_large_tree_warning(self, count: int) -> None:
        self.lbl_large_tree.setText(f"⚠️ Large Tree ({count:,} nodes)")
        self.lbl_large_tree.show()
        # Auto-hide after 8 seconds
        QTimer.singleShot(8000, self.lbl_large_tree.hide)

    def show_elevation_warning(self, show: bool = True) -> None:
        if show:
            self.btn_elevation.show()
            self.lbl_msg.setText("⚠️ Target app requires Administrator rights to inspect.")
        else:
            self.btn_elevation.hide()
