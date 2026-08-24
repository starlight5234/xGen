"""
xGen Main Toolbar Widget.
Provides session indicator, window switcher, tree refresh, inspect toggle, freeze toggle, and timed capture triggers.
"""

from __future__ import annotations

from typing import List, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolBar,
    QWidget,
)

from xgen.core.session_manager import SessionState, WindowInfo


class Toolbar(QToolBar):
    """Application top toolbar with action triggers and context selectors."""
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    inspect_toggled = pyqtSignal(bool)
    window_switched = pyqtSignal(str)          # handle
    freeze_toggled = pyqtSignal(bool)
    timed_capture_start = pyqtSignal(int)      # delay seconds
    pin_toggled = pyqtSignal(bool)             # always on top
    legend_requested = pyqtSignal()            # open XPath legend guide dialog

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("QToolBar { background: #12151b; border-bottom: 1px solid #1e222b; spacing: 6px; padding: 2px 4px; }")
        container = QWidget(self)
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # 1. Session Status Pill
        self.btn_session = QPushButton("🔴 Disconnected")
        self.btn_session.setStyleSheet(
            "QPushButton { background: #201314; color: #f87171; border: 1px solid #7f1d1d; border-radius: 13px; padding: 4px 12px; font-weight: 600; font-size: 11px; }"
            "QPushButton:hover { background: #2d1618; border-color: #ef4444; }"
        )
        self.btn_session.clicked.connect(self.connect_requested.emit)
        layout.addWidget(self.btn_session)

        # 1b. Disconnect Button
        self.btn_disconnect = QPushButton("🔌 Disconnect")
        self.btn_disconnect.setToolTip("Disconnect and close active Appium session")
        self.btn_disconnect.setStyleSheet(
            "QPushButton { background: #2d1618; color: #fca5a5; border: 1px solid #7f1d1d; border-radius: 13px; padding: 4px 10px; font-weight: 600; font-size: 11px; }"
            "QPushButton:hover { background: #991b1b; color: #ffffff; border-color: #ef4444; }"
        )
        self.btn_disconnect.clicked.connect(self.disconnect_requested.emit)
        self.btn_disconnect.setVisible(False)
        layout.addWidget(self.btn_disconnect)

        # 2. Window Switcher Dropdown
        self.combo_windows = QComboBox()
        self.combo_windows.setMinimumWidth(190)
        self.combo_windows.setStyleSheet(
            "QComboBox { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 4px 10px; font-size: 11px; }"
            "QComboBox:hover { border-color: #3b82f6; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
            "QComboBox QAbstractItemView { background: #181c24; color: #f1f5f9; selection-background-color: #2563eb; selection-color: #ffffff; border: 1px solid #2a3140; border-radius: 4px; padding: 4px; }"
        )
        self.combo_windows.currentIndexChanged.connect(self._on_window_selected)
        layout.addWidget(self.combo_windows)

        # Separator line
        sep1 = QLabel("│")
        sep1.setStyleSheet("color: #2a3140; font-size: 13px;")
        layout.addWidget(sep1)

        # 3. Refresh Tree Button
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setToolTip("Fetch fresh UI tree snapshot (Ctrl+R)")
        self.btn_refresh.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #3b82f6; }"
        )
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.btn_refresh)

        # 4. Inspect Toggle Button (F3)
        self.btn_inspect = QPushButton("🎯 Inspect (F3)")
        self.btn_inspect.setCheckable(True)
        self.btn_inspect.setToolTip("Toggle Inspect Hover Mode (F3)")
        self.btn_inspect.setStyleSheet(
            "QPushButton { background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 14px; font-weight: 600; font-size: 11px; }"
            "QPushButton:hover { background: #0284c7; color: #ffffff; }"
            "QPushButton:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444); color: #ffffff; border: 1px solid #f87171; }"
            "QPushButton:checked:hover { background: #b91c1c; }"
        )
        self.btn_inspect.toggled.connect(self._on_inspect_clicked)
        layout.addWidget(self.btn_inspect)

        # 5. Freeze Tree Toggle (F4 snapshot)
        self.btn_freeze = QPushButton("🔒 Freeze")
        self.btn_freeze.setCheckable(True)
        self.btn_freeze.setToolTip("Freeze UI tree snapshot (F4 for instant hover capture)")
        self.btn_freeze.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #f59e0b; }"
            "QPushButton:checked { background: #451a03; color: #fbbf24; border-color: #f59e0b; font-weight: 600; }"
        )
        self.btn_freeze.toggled.connect(self.freeze_toggled.emit)
        layout.addWidget(self.btn_freeze)

        # 6. Timed Capture Button
        self.btn_timed = QPushButton("⏱ Timed 5s")
        self.btn_timed.setToolTip("Set 5-second countdown to interact with app before auto-capture")
        self.btn_timed.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #3b82f6; }"
        )
        self.btn_timed.clicked.connect(lambda: self.timed_capture_start.emit(5))
        layout.addWidget(self.btn_timed)

        # 7. Pin on Top (Always on Top) Toggle
        self.btn_pin = QPushButton("📌 Pin on Top")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip("Keep xGen floating on top of all windows while inspecting")
        self.btn_pin.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #8b5cf6; }"
            "QPushButton:checked { background: #3b0764; color: #d8b4fe; border-color: #8b5cf6; font-weight: 600; }"
        )
        self.btn_pin.toggled.connect(self.pin_toggled.emit)
        layout.addWidget(self.btn_pin)

        layout.addStretch()

        # 8. Interactive XPath Guide Button
        self.btn_legend = QPushButton("📖 XPath Guide")
        self.btn_legend.setToolTip("Open comprehensive XPath Guide: Badges, Loc Risk, Stability Scores, and Tiers")
        self.btn_legend.setStyleSheet(
            "QPushButton { background: #181c24; color: #60a5fa; border: 1px solid #2e384d; border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #1e293b; color: #93c5fd; border-color: #3b82f6; }"
        )
        self.btn_legend.clicked.connect(self.legend_requested.emit)
        layout.addWidget(self.btn_legend)

        self.addWidget(container)

    def set_session_state(self, state_str: str, app_name: str = "") -> None:
        if state_str == SessionState.CONNECTED.value:
            label = f"✅ {app_name or 'Connected'}"
            self.btn_session.setText(label)
            self.btn_session.setStyleSheet(
                "QPushButton { background: #1b382b; color: #4caf50; border: 1px solid #2e7d32; border-radius: 12px; padding: 4px 12px; font-weight: bold; font-size: 11px; }"
                "QPushButton:hover { background: #234737; }"
            )
            self.btn_disconnect.setVisible(True)
        elif state_str == SessionState.CONNECTING.value:
            self.btn_session.setText("🟡 Connecting...")
            self.btn_session.setStyleSheet(
                "QPushButton { background: #3a321d; color: #ffca28; border: 1px solid #f57f17; border-radius: 12px; padding: 4px 12px; font-weight: bold; font-size: 11px; }"
            )
            self.btn_disconnect.setVisible(False)
        elif state_str == SessionState.LOST.value:
            self.btn_session.setText("⚠️ Session Lost")
            self.btn_session.setStyleSheet(
                "QPushButton { background: #3a1d1d; color: #ff5252; border: 1px solid #c62828; border-radius: 12px; padding: 4px 12px; font-weight: bold; font-size: 11px; }"
            )
            self.btn_disconnect.setVisible(False)
        else:
            self.btn_session.setText("🔴 Disconnected")
            self.btn_session.setStyleSheet(
                "QPushButton { background: #26292e; color: #ff5252; border: 1px solid #3c4048; border-radius: 12px; padding: 4px 12px; font-weight: bold; font-size: 11px; }"
                "QPushButton:hover { background: #32363e; }"
            )
            self.btn_disconnect.setVisible(False)

    def update_windows_list(self, windows: List[WindowInfo]) -> None:
        self.combo_windows.blockSignals(True)
        self.combo_windows.clear()

        active_idx = 0
        for idx, w in enumerate(windows):
            title = w.title or f"Window {w.handle}"
            self.combo_windows.addItem(f"🪟 {title}", w.handle)
            if w.is_active:
                active_idx = idx

        if windows:
            self.combo_windows.setCurrentIndex(active_idx)
        self.combo_windows.blockSignals(False)

    def set_inspect_active(self, active: bool) -> None:
        self.btn_inspect.blockSignals(True)
        self.btn_inspect.setChecked(active)
        if active:
            self.btn_inspect.setText("🛑 Stop Inspect")
        else:
            self.btn_inspect.setText("🎯 Inspect (F3)")
        self.btn_inspect.blockSignals(False)

    def set_finding_xpath(self, finding: bool) -> None:
        """Update inspect button to show finding/generating state and restore afterwards."""
        self.btn_inspect.blockSignals(True)
        if finding:
            self.btn_inspect.setText("⏳ Finding XPath...")
            self.btn_inspect.setStyleSheet(
                "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f766e, stop:1 #0d9488); color: #ffffff; border: 1px solid #2dd4bf; border-radius: 6px; padding: 4px 14px; font-weight: 600; font-size: 11px; }"
            )
        else:
            is_active = self.btn_inspect.isChecked()
            self.btn_inspect.setStyleSheet(
                "QPushButton { background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 14px; font-weight: 600; font-size: 11px; }"
                "QPushButton:hover { background: #0284c7; color: #ffffff; }"
                "QPushButton:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444); color: #ffffff; border: 1px solid #f87171; }"
                "QPushButton:checked:hover { background: #b91c1c; }"
            )
            if is_active:
                self.btn_inspect.setText("🛑 Stop Inspect")
            else:
                self.btn_inspect.setText("🎯 Inspect (F3)")
        self.btn_inspect.blockSignals(False)

    def _on_inspect_clicked(self, checked: bool) -> None:
        self.set_inspect_active(checked)
        self.inspect_toggled.emit(checked)

    def _on_window_selected(self, index: int) -> None:
        if index >= 0:
            handle = self.combo_windows.itemData(index)
            if handle:
                self.window_switched.emit(str(handle))
