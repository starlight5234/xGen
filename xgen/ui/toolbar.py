"""
xGen Main Toolbar Widget.
Provides session indicator, window switcher, tree refresh, inspect toggle, freeze toggle, and timed capture triggers.
"""

from __future__ import annotations

from typing import List, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolBar,
    QWidget,
)

from xgen.core.session_manager import SessionState, WindowInfo


class StatusDot(QPushButton):
    """
    Precision-rendered, mathematically centered status dot with concentric ring.
    Eliminates text emoji glyph font baseline offsets completely.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dot_color = QColor("#ef4444")
        self._bg_color = QColor("#201314")
        self._border_color = QColor("#7f1d1d")
        self._hover_bg = QColor("#2d1618")
        self._hover_border = QColor("#ef4444")
        self._is_hovered = False
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def enterEvent(self, event) -> None:
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def set_colors(self, dot: str, bg: str, border: str, hover_bg: str, hover_border: str) -> None:
        self._dot_color = QColor(dot)
        self._bg_color = QColor(bg)
        self._border_color = QColor(border)
        self._hover_bg = QColor(hover_bg)
        self._hover_border = QColor(hover_border)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = self._hover_bg if self._is_hovered else self._bg_color
        border = self._hover_border if self._is_hovered else self._border_color

        w = self.width()
        h = self.height()

        # Outer concentric circle (20x20 centered in 24x24)
        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawEllipse(2, 2, w - 4, h - 4)

        # Inner solid dot (8x8 centered in 24x24: 8px margin all sides)
        cx = w // 2
        cy = h // 2
        r = 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._dot_color))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)


class Toolbar(QToolBar):
    """Application top toolbar with action triggers and context selectors."""
    connect_requested = pyqtSignal()           # open full session dialog
    fast_connect_requested = pyqtSignal()      # quick toggle connect
    disconnect_requested = pyqtSignal()        # quick disconnect
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
        self._current_state = SessionState.DISCONNECTED.value
        self._current_app_name = ""
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("QToolBar { background: #12151b; border-bottom: 1px solid #1e222b; spacing: 0px; padding: 2px 0px; }")
        container = QWidget(self)
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(0)

        # === 1. Left Section: Session Dot, Settings, and Window Target ===
        self.left_container = QWidget()
        self.left_container.setStyleSheet("background: transparent;")
        self.left_container.setFixedWidth(350)  # Matches minimum width of Tree Panel (350px)
        left_layout = QHBoxLayout(self.left_container)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(6)

        # 1a. Precision Vector Status Dot (Fast Connect / Disconnect)
        self.btn_status_dot = StatusDot()
        self.btn_status_dot.setToolTip("Disconnected\nClick to Quick-Connect to last target")
        self.btn_status_dot.clicked.connect(self._on_status_dot_clicked)
        left_layout.addWidget(self.btn_status_dot)

        # 1b. Dedicated Session Management / Config Button
        self.btn_session_config = QPushButton("⚙️ Session")
        self.btn_session_config.setFixedHeight(26)
        self.btn_session_config.setFixedWidth(82)
        self.btn_session_config.setToolTip("Configure Appium session, capabilities, and target apps")
        self.btn_session_config.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 2px 8px 3px 8px; font-size: 11px; font-weight: 500; text-align: center; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #3b82f6; }"
        )
        self.btn_session_config.clicked.connect(self.connect_requested.emit)
        left_layout.addWidget(self.btn_session_config)

        # 1c. Window Switcher Dropdown (Fills 222px across the 350px container)
        self.combo_windows = QComboBox()
        self.combo_windows.setFixedHeight(26)
        self.combo_windows.setFixedWidth(222)
        self.combo_windows.setToolTip("Switch active window inspection target")
        self.combo_windows.setStyleSheet(
            "QComboBox { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 1px 10px; font-size: 11px; }"
            "QComboBox:hover { border-color: #3b82f6; }"
            "QComboBox::drop-down { border: none; width: 16px; }"
            "QComboBox QAbstractItemView { background: #14171e; color: #cbd5e1; selection-background-color: #2563eb; selection-color: #ffffff; border: 1px solid #28303f; border-radius: 6px; padding: 4px; outline: none; }"
            "QComboBox QAbstractItemView::item { min-height: 24px; padding: 4px 10px; border-radius: 4px; border-bottom: 1px solid #1e2430; margin: 1px 0px; }"
            "QComboBox QAbstractItemView::item:hover { background-color: #1e2533; color: #ffffff; }"
            "QComboBox QAbstractItemView::item:selected { background-color: #2563eb; color: #ffffff; font-weight: 500; }"
        )
        self.combo_windows.currentIndexChanged.connect(self._on_window_selected)
        if self.combo_windows.view() and self.combo_windows.view().window():
            self.combo_windows.view().window().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.combo_windows.view().window().setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        left_layout.addWidget(self.combo_windows)

        layout.addWidget(self.left_container)

        # Space before center buttons
        layout.addStretch(1)

        # === 2. Center Section: Primary Action & Inspection Tools ===
        self.center_container = QWidget()
        self.center_container.setStyleSheet("background: transparent;")
        center_layout = QHBoxLayout(self.center_container)
        center_layout.setContentsMargins(8, 0, 8, 0)
        center_layout.setSpacing(6)

        # 2a. Refresh Tree Button (Placed first on left of Inspect)
        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setFixedHeight(26)
        self.btn_refresh.setToolTip("Fetch fresh UI tree snapshot (Ctrl+R)")
        self.btn_refresh.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 2px 11px 3px 11px; font-size: 11px; font-weight: 500; text-align: center; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #3b82f6; }"
        )
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        center_layout.addWidget(self.btn_refresh)

        # 2b. Inspect Toggle Button (F3)
        self.btn_inspect = QPushButton("🎯 Inspect (F3)")
        self.btn_inspect.setFixedHeight(26)
        self.btn_inspect.setCheckable(True)
        self.btn_inspect.setToolTip("Toggle Inspect Hover Mode (F3)")
        self.btn_inspect.setStyleSheet(
            "QPushButton { background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 2px 13px 3px 13px; font-weight: 600; font-size: 11px; text-align: center; }"
            "QPushButton:hover { background: #0284c7; color: #ffffff; }"
            "QPushButton:checked { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc2626, stop:1 #ef4444); color: #ffffff; border: 1px solid #f87171; }"
            "QPushButton:checked:hover { background: #b91c1c; }"
        )
        self.btn_inspect.toggled.connect(self._on_inspect_clicked)
        center_layout.addWidget(self.btn_inspect)

        # 2c. Freeze Tree Toggle (F4 snapshot)
        self.btn_freeze = QPushButton("🔒 Freeze")
        self.btn_freeze.setFixedHeight(26)
        self.btn_freeze.setCheckable(True)
        self.btn_freeze.setToolTip("Freeze UI tree snapshot (F4 for instant hover capture)")
        self.btn_freeze.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 2px 11px 3px 11px; font-size: 11px; font-weight: 500; text-align: center; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #f59e0b; }"
            "QPushButton:checked { background: #451a03; color: #fbbf24; border-color: #f59e0b; font-weight: 600; }"
        )
        self.btn_freeze.toggled.connect(self.freeze_toggled.emit)
        center_layout.addWidget(self.btn_freeze)

        # 2d. Timed Capture Button
        self.btn_timed = QPushButton("⏱ 5s")
        self.btn_timed.setFixedHeight(26)
        self.btn_timed.setToolTip("Set 5-second countdown to interact with app before auto-capture")
        self.btn_timed.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 2px 11px 3px 11px; font-size: 11px; font-weight: 500; text-align: center; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #3b82f6; }"
        )
        self.btn_timed.clicked.connect(lambda: self.timed_capture_start.emit(5))
        center_layout.addWidget(self.btn_timed)

        # 2e. Pin on Top (Always on Top) Toggle
        self.btn_pin = QPushButton("📌 Pin")
        self.btn_pin.setFixedHeight(26)
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip("Keep xGen floating on top of all windows while inspecting")
        self.btn_pin.setStyleSheet(
            "QPushButton { background: #181c24; color: #cbd5e1; border: 1px solid #2a3140; border-radius: 6px; padding: 2px 11px 3px 11px; font-size: 11px; font-weight: 500; text-align: center; }"
            "QPushButton:hover { background: #222834; color: #ffffff; border-color: #8b5cf6; }"
            "QPushButton:checked { background: #3b0764; color: #d8b4fe; border-color: #8b5cf6; font-weight: 600; }"
        )
        self.btn_pin.toggled.connect(self.pin_toggled.emit)
        center_layout.addWidget(self.btn_pin)

        layout.addWidget(self.center_container)

        # Space after center buttons
        layout.addStretch(1)

        # === 3. Right Section: Pinned XPath Guide ===
        self.btn_legend = QPushButton("📖 Guide")
        self.btn_legend.setFixedHeight(26)
        self.btn_legend.setToolTip("Open XPath Guide: Badges, Loc Risk, Stability Scores, and Tiers")
        self.btn_legend.setStyleSheet(
            "QPushButton { background: #181c24; color: #60a5fa; border: 1px solid #2e384d; border-radius: 6px; padding: 2px 13px 3px 13px; font-size: 11px; font-weight: 600; text-align: center; }"
            "QPushButton:hover { background: #1e293b; color: #93c5fd; border-color: #3b82f6; }"
        )
        self.btn_legend.clicked.connect(self.legend_requested.emit)
        layout.addWidget(self.btn_legend)

        self.addWidget(container)

    def _on_status_dot_clicked(self) -> None:
        """1-Click Quick Action: Disconnect if active, or Fast-Connect if disconnected."""
        if self._current_state == SessionState.CONNECTING.value:
            return

        if self._current_state == SessionState.CONNECTED.value:
            self.disconnect_requested.emit()
        else:
            # Immediately lock status dot into connecting state to prevent duplicate clicks
            self.set_session_state(SessionState.CONNECTING.value)
            self.fast_connect_requested.emit()

    def set_collapsed_state(self, collapsed: bool) -> None:
        """Toolbar maintains stable geometry independently of tree panel collapse state."""
        pass

    def set_left_width(self, width: int) -> None:
        """Toolbar maintains stable geometry independently of splitter movements."""
        pass

    def set_session_state(self, state_str: str, app_name: str = "") -> None:
        self._current_state = state_str
        self._current_app_name = app_name

        if state_str == SessionState.CONNECTING.value:
            self.btn_status_dot.setEnabled(False)
            self.btn_status_dot.setCursor(Qt.CursorShape.WaitCursor)
        else:
            self.btn_status_dot.setEnabled(True)
            self.btn_status_dot.setCursor(Qt.CursorShape.PointingHandCursor)

        if state_str == SessionState.CONNECTED.value:
            name = app_name or "Desktop Root"
            self.btn_status_dot.setToolTip(f"🟢 Connected to: {name}\nClick to Disconnect")
            self.btn_status_dot.set_colors(
                dot="#10b981",
                bg="#064e3b",
                border="#059669",
                hover_bg="#047857",
                hover_border="#34d399"
            )
        elif state_str == SessionState.CONNECTING.value:
            self.btn_status_dot.setToolTip("🟡 Connecting to Appium...")
            self.btn_status_dot.set_colors(
                dot="#fbbf24",
                bg="#451a03",
                border="#b45309",
                hover_bg="#78350f",
                hover_border="#f59e0b"
            )
        elif state_str == SessionState.LOST.value:
            self.btn_status_dot.setToolTip("⚠️ Session Lost\nClick to Reconnect")
            self.btn_status_dot.set_colors(
                dot="#f87171",
                bg="#450a0a",
                border="#dc2626",
                hover_bg="#5c0f0f",
                hover_border="#ef4444"
            )
        else:
            self.btn_status_dot.setToolTip("🔴 Disconnected\nClick to Quick-Connect to last target")
            self.btn_status_dot.set_colors(
                dot="#ef4444",
                bg="#201314",
                border="#7f1d1d",
                hover_bg="#2d1618",
                hover_border="#ef4444"
            )

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
