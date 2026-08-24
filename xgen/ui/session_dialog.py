"""
Session Setup and Connection Dialog.
Allows user to launch apps, attach to windows, or inspect Desktop root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from xgen.config import ConfigManager, RecentSession, XGenConfig
from xgen.core.session_manager import SessionManager


class SessionDialog(QDialog):
    """Modal dialog to configure and initiate an Appium Windows Driver session."""
    session_requested = pyqtSignal(object)  # XGenConfig

    def __init__(self, config: XGenConfig, session_manager: SessionManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.session_manager = session_manager
        self.setWindowTitle("xGen — Connect Session")
        self.setMinimumWidth(540)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background: #0f1115; color: #f1f5f9; font-family: 'Segoe UI', system-ui, sans-serif; }
            QGroupBox { background: #14171e; border: 1px solid #232834; border-radius: 8px; margin-top: 14px; padding-top: 16px; padding-left: 10px; padding-right: 10px; padding-bottom: 10px; font-weight: 600; color: #93c5fd; font-size: 11px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 0 4px; background: transparent; }
            QRadioButton { color: #cbd5e1; font-size: 11px; spacing: 8px; padding: 4px 0; }
            QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; border: 1px solid #3b82f6; background: #181c24; }
            QRadioButton::indicator:checked { background: #3b82f6; border: 3px solid #14171e; }
            QRadioButton:hover { color: #ffffff; }
            QLineEdit { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 6px 10px; font-size: 11px; }
            QLineEdit:focus { border-color: #3b82f6; }
            QLineEdit:disabled { background: #111317; color: #475569; border-color: #1e222b; }
            QLabel { color: #cbd5e1; font-size: 11px; }
            QLabel:disabled { color: #475569; }
            QComboBox { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 6px 10px; font-size: 11px; }
            QComboBox:hover { border-color: #3b82f6; }
            QComboBox QAbstractItemView { background: #181c24; color: #f1f5f9; selection-background-color: #2563eb; selection-color: #ffffff; border: 1px solid #2a3140; border-radius: 4px; padding: 4px; }
            QPushButton { background: #1e2430; color: #cbd5e1; border: 1px solid #2e384d; border-radius: 6px; padding: 6px 14px; font-size: 11px; font-weight: 500; }
            QPushButton:hover { background: #2b3548; color: #ffffff; border-color: #3b82f6; }
        """)

        self._init_ui()
        self._populate_from_config(config)
        self.check_server_status()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Mode Selection Group
        mode_group = QGroupBox("Inspection Target Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.radio_root = QRadioButton("Desktop Root (Recommended — inspect multi-window apps like Teams/Outlook)")
        self.radio_launch = QRadioButton("Launch Application (.exe path)")
        self.radio_attach = QRadioButton("Attach to Running Top-Level Window (HWND)")

        self.radio_root.setChecked(True)
        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.radio_root, 1)
        self.btn_group.addButton(self.radio_launch, 2)
        self.btn_group.addButton(self.radio_attach, 3)
        self.btn_group.buttonClicked.connect(self._on_mode_changed)

        mode_layout.addWidget(self.radio_root)
        mode_layout.addWidget(self.radio_launch)
        mode_layout.addWidget(self.radio_attach)
        main_layout.addWidget(mode_group)

        # 2. Connection Details Form
        form_group = QGroupBox("Target Configuration")
        form_layout = QFormLayout(form_group)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # App path field + Browse button
        self.app_path_edit = QLineEdit()
        self.app_path_edit.setPlaceholderText("C:\\Program Files\\...\\app.exe")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_app_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.app_path_edit)
        path_row.addWidget(btn_browse)
        self.lbl_app_path = QLabel("App Executable:")
        form_layout.addRow(self.lbl_app_path, path_row)

        # Window handle field
        self.window_handle_edit = QLineEdit()
        self.window_handle_edit.setPlaceholderText("e.g. 0x001A0B2C or 1706796")
        self.lbl_window_handle = QLabel("Window Handle:")
        form_layout.addRow(self.lbl_window_handle, self.window_handle_edit)

        # Appium Server URL
        self.appium_url_edit = QLineEdit("http://127.0.0.1:4723")
        btn_test_url = QPushButton("Ping Status")
        btn_test_url.clicked.connect(self.check_server_status)
        url_row = QHBoxLayout()
        url_row.addWidget(self.appium_url_edit)
        url_row.addWidget(btn_test_url)
        form_layout.addRow("Appium URL:", url_row)

        main_layout.addWidget(form_group)

        # 3. Recent Sessions
        recent_group = QGroupBox("Recent Configurations")
        recent_layout = QHBoxLayout(recent_group)
        self.recent_combo = QComboBox()
        self.recent_combo.setPlaceholderText("Select a recent session...")
        btn_load_recent = QPushButton("Load")
        btn_load_recent.clicked.connect(self._load_selected_recent)
        recent_layout.addWidget(self.recent_combo, 1)
        recent_layout.addWidget(btn_load_recent)
        main_layout.addWidget(recent_group)

        # 4. Status Indicator Banner
        self.lbl_status = QLabel("Checking Appium server status...")
        self.lbl_status.setStyleSheet("background: #1e2433; color: #94a3b8; border: 1px solid #2e384d; border-radius: 6px; padding: 6px 10px; font-size: 11px;")
        main_layout.addWidget(self.lbl_status)

        # 5. Dialog Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("QPushButton { background: #181c24; color: #94a3b8; border: 1px solid #2a3140; border-radius: 6px; padding: 7px 18px; font-size: 11px; font-weight: 500; } QPushButton:hover { background: #222834; color: #f1f5f9; }")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setDefault(True)
        self.btn_connect.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); color: #ffffff; border: 1px solid #60a5fa; border-radius: 6px; padding: 7px 22px; font-size: 11px; font-weight: bold; } QPushButton:hover { background: #1d4ed8; }")
        self.btn_connect.clicked.connect(self._on_connect_clicked)

        button_row.addWidget(self.btn_cancel)
        button_row.addWidget(self.btn_connect)
        main_layout.addLayout(button_row)

        self._update_field_visibility()

    def _populate_from_config(self, cfg: XGenConfig) -> None:
        self.appium_url_edit.setText(cfg.appium_url or "http://127.0.0.1:4723")
        self.app_path_edit.setText(cfg.app_path or "")
        self.window_handle_edit.setText(cfg.app_top_level_window or "")

        if cfg.app_top_level_window:
            self.radio_attach.setChecked(True)
        elif cfg.app_path:
            self.radio_launch.setChecked(True)
        else:
            self.radio_root.setChecked(True)

        self._populate_recent_dropdown(cfg)
        self._update_field_visibility()

    def _populate_recent_dropdown(self, cfg: XGenConfig) -> None:
        self.recent_combo.clear()
        for s in cfg.recent_sessions:
            label = f"{s.name} ({s.app_path or s.app_top_level_window or 'Root'})"
            self.recent_combo.addItem(label, s)

    def _update_field_visibility(self) -> None:
        is_launch = self.radio_launch.isChecked()
        is_attach = self.radio_attach.isChecked()

        self.lbl_app_path.setEnabled(is_launch)
        self.app_path_edit.setEnabled(is_launch)
        self.lbl_window_handle.setEnabled(is_attach)
        self.window_handle_edit.setEnabled(is_attach)

    def _on_mode_changed(self) -> None:
        self._update_field_visibility()

    def _browse_app_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Target Application Executable",
            "C:\\Program Files",
            "Executables (*.exe);;All Files (*.*)"
        )
        if path:
            self.app_path_edit.setText(path)

    def _load_selected_recent(self) -> None:
        idx = self.recent_combo.currentIndex()
        if idx < 0:
            return
        s: RecentSession = self.recent_combo.itemData(idx)
        if not s:
            return

        self.appium_url_edit.setText(s.appium_url)
        self.app_path_edit.setText(s.app_path)
        self.window_handle_edit.setText(s.app_top_level_window)

        if s.app_top_level_window:
            self.radio_attach.setChecked(True)
        elif s.app_path:
            self.radio_launch.setChecked(True)
        else:
            self.radio_root.setChecked(True)
        self._update_field_visibility()

    def check_server_status(self) -> None:
        url = self.appium_url_edit.text().strip() or "http://127.0.0.1:4723"
        is_running, msg = SessionManager.check_server_status(url, timeout_seconds=1.5)
        if is_running:
            self.lbl_status.setText(f"✅ {msg}")
            self.lbl_status.setStyleSheet("background: #064e3b; color: #34d399; border: 1px solid #059669; border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11px;")
        else:
            self.lbl_status.setText(f"❌ {msg}")
            self.lbl_status.setStyleSheet("background: #450a0a; color: #f87171; border: 1px solid #dc2626; border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11px;")

    def _on_connect_clicked(self) -> None:
        url = self.appium_url_edit.text().strip() or "http://127.0.0.1:4723"
        app_path = ""
        app_window = ""

        if self.radio_launch.isChecked():
            app_path = self.app_path_edit.text().strip()
            if not app_path:
                self.lbl_status.setText("⚠️ Please specify an application path.")
                self.lbl_status.setStyleSheet("background: #451a03; color: #fbbf24; border: 1px solid #b45309; border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11px;")
                return
        elif self.radio_attach.isChecked():
            app_window = self.window_handle_edit.text().strip()
            if not app_window:
                self.lbl_status.setText("⚠️ Please specify a top-level window handle.")
                self.lbl_status.setStyleSheet("background: #451a03; color: #fbbf24; border: 1px solid #b45309; border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11px;")
                return
        else:
            app_path = "Root"

        # Update config object
        self.config.appium_url = url
        self.config.app_path = app_path if app_path != "Root" else ""
        self.config.app_top_level_window = app_window

        # Add to recents
        session_name = Path(app_path).stem if app_path and app_path != "Root" else (f"Window {app_window}" if app_window else "Desktop Root")
        recent = RecentSession(
            name=session_name,
            app_path=self.config.app_path,
            app_top_level_window=app_window,
            appium_url=url
        )
        ConfigManager.add_recent_session(self.config, recent)
        ConfigManager.save(self.config)

        self.session_requested.emit(self.config)
        self.accept()
