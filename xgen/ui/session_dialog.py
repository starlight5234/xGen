"""
Session Setup and Connection Dialog.
Allows user to launch apps, attach to windows, or inspect Desktop root.
"""

import datetime
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
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


class PingWorker(QObject):
    """Background worker to check Appium reachability without UI blocking or flicker."""
    finished = pyqtSignal(bool, str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        is_running, msg = SessionManager.check_server_status(self.url, timeout_seconds=1.5)
        if not self._is_cancelled:
            try:
                self.finished.emit(is_running, msg)
            except RuntimeError:
                pass


class SessionDialog(QDialog):
    """Modal dialog to configure and initiate an Appium Windows Driver session."""
    session_requested = pyqtSignal(object)  # XGenConfig

    def __init__(self, config: XGenConfig, session_manager: SessionManager, parent: Optional[QWidget] = None, auto_check: bool = True):
        super().__init__(parent)
        self.config = config
        self.session_manager = session_manager
        self._ping_thread: Optional[QThread] = None
        self._ping_worker: Optional[PingWorker] = None
        self.setWindowTitle("xGen — Connect Session")
        self.setMinimumWidth(540)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background: #0f1115; color: #f1f5f9; font-family: 'Segoe UI', system-ui, sans-serif; }
            QFrame#card { background-color: #14171e; border: 1px solid #232834; border-radius: 8px; }
            QLabel#section_title { color: #60a5fa; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; margin-top: 4px; }
            QRadioButton { color: #cbd5e1; font-size: 11px; spacing: 8px; padding: 3px 0; }
            QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; border: 1px solid #475569; background: #181c24; }
            QRadioButton::indicator:hover { border-color: #3b82f6; }
            QRadioButton::indicator:checked { width: 14px; height: 14px; border-radius: 7px; border: 1px solid #3b82f6; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #3b82f6, stop:0.55 #3b82f6, stop:0.6 #181c24, stop:1.0 #181c24); }
            QRadioButton:hover { color: #ffffff; }
            QLineEdit { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 6px 10px; font-size: 11px; }
            QLineEdit:focus { border-color: #3b82f6; }
            QLineEdit:disabled { background: #111317; color: #475569; border-color: #1e222b; }
            QLabel { color: #cbd5e1; font-size: 11px; }
            QLabel:disabled { color: #475569; }
            QComboBox { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 6px 10px; font-size: 11px; }
            QComboBox:hover { border-color: #3b82f6; }
            QComboBox QAbstractItemView { background: #14171e; color: #cbd5e1; selection-background-color: #2563eb; selection-color: #ffffff; border: 1px solid #28303f; border-radius: 6px; padding: 4px; outline: none; }
            QComboBox QAbstractItemView::item { min-height: 24px; padding: 4px 10px; border-radius: 4px; border-bottom: 1px solid #1e2430; margin: 1px 0px; }
            QComboBox QAbstractItemView::item:hover { background-color: #1e2533; color: #ffffff; }
            QComboBox QAbstractItemView::item:selected { background-color: #2563eb; color: #ffffff; font-weight: 500; }
            QPushButton { background: #1e2430; color: #cbd5e1; border: 1px solid #2e384d; border-radius: 6px; padding: 6px 14px; font-size: 11px; font-weight: 500; }
            QPushButton:hover { background: #2b3548; color: #ffffff; border-color: #3b82f6; }
        """)

        self._init_ui()
        self._populate_from_config(config)
        if auto_check:
            self.check_server_status()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Mode Selection Card
        lbl_mode = QLabel("INSPECTION TARGET MODE")
        lbl_mode.setObjectName("section_title")
        main_layout.addWidget(lbl_mode)

        mode_card = QFrame()
        mode_card.setObjectName("card")
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(12, 10, 12, 10)
        mode_layout.setSpacing(6)

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
        main_layout.addWidget(mode_card)

        # 2. Connection Details Form Card
        lbl_target = QLabel("TARGET CONFIGURATION")
        lbl_target.setObjectName("section_title")
        main_layout.addWidget(lbl_target)

        form_card = QFrame()
        form_card.setObjectName("card")
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_layout.setSpacing(8)
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
        self.btn_test_url = QPushButton("Ping Status")
        self.btn_test_url.setFixedWidth(100)
        self.btn_test_url.clicked.connect(self.check_server_status)
        url_row = QHBoxLayout()
        url_row.addWidget(self.appium_url_edit)
        url_row.addWidget(self.btn_test_url)
        form_layout.addRow("Appium URL:", url_row)

        main_layout.addWidget(form_card)

        # 3. Recent Configurations Card
        lbl_recent = QLabel("RECENT CONFIGURATIONS")
        lbl_recent.setObjectName("section_title")
        main_layout.addWidget(lbl_recent)

        recent_card = QFrame()
        recent_card.setObjectName("card")
        recent_layout = QHBoxLayout(recent_card)
        recent_layout.setContentsMargins(12, 10, 12, 10)
        recent_layout.setSpacing(8)
        self.recent_combo = QComboBox()
        self.recent_combo.setPlaceholderText("Select a recent session...")
        if self.recent_combo.view() and self.recent_combo.view().window():
            self.recent_combo.view().window().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.recent_combo.view().window().setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        btn_load_recent = QPushButton("Load")
        btn_load_recent.clicked.connect(self._load_selected_recent)
        recent_layout.addWidget(self.recent_combo, 1)
        recent_layout.addWidget(btn_load_recent)
        main_layout.addWidget(recent_card)

        # 4. Options / Preferences
        self.chk_confirm_disconnect = QCheckBox("Ask confirmation before disconnecting active session")
        self.chk_confirm_disconnect.setToolTip("Show a confirmation prompt when clicking the connected status dot to disconnect")
        self.chk_confirm_disconnect.setStyleSheet("""
            QCheckBox { color: #cbd5e1; font-size: 11px; padding: 2px 0; }
            QCheckBox:hover { color: #ffffff; }
            QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #334155; background: #181c24; }
            QCheckBox::indicator:checked { background: #2563eb; border-color: #3b82f6; }
        """)
        self.chk_confirm_disconnect.toggled.connect(self._on_confirm_disconnect_toggled)
        main_layout.addWidget(self.chk_confirm_disconnect)

        # 5. Status Indicator Banner
        self.lbl_status = QLabel("Checking Appium server status...")
        self.lbl_status.setStyleSheet("background: #1e2433; color: #94a3b8; border: 1px solid #2e384d; border-radius: 6px; padding: 6px 10px; font-size: 11px;")
        main_layout.addWidget(self.lbl_status)

        # 6. Dialog Buttons
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

    def _on_confirm_disconnect_toggled(self, checked: bool) -> None:
        self.config.confirm_disconnect = checked
        ConfigManager.save(self.config)

    def _populate_from_config(self, cfg: XGenConfig) -> None:
        self.appium_url_edit.setText(cfg.appium_url or "http://127.0.0.1:4723")
        self.app_path_edit.setText(cfg.app_path or "")
        self.window_handle_edit.setText(cfg.app_top_level_window or "")
        self.chk_confirm_disconnect.setChecked(getattr(cfg, "confirm_disconnect", True))

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

        # Prevent duplicate in-flight pings
        if self._ping_thread and self._ping_thread.isRunning():
            return

        if hasattr(self, "btn_test_url"):
            self.btn_test_url.setEnabled(False)
            self.btn_test_url.setText("Pinging...")

        self.lbl_status.setText(f"⏳ Pinging Appium server at {url}...")

        self._ping_thread = QThread(self)
        self._ping_worker = PingWorker(url)
        self._ping_worker.moveToThread(self._ping_thread)

        self._ping_thread.started.connect(self._ping_worker.run)
        self._ping_worker.finished.connect(self._on_ping_finished)
        self._ping_worker.finished.connect(self._ping_thread.quit)
        self._ping_thread.start()

    def _on_ping_finished(self, is_running: bool, msg: str) -> None:
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        if is_running:
            self.lbl_status.setText(f"[{now_str}] ✅ {msg}")
            self.lbl_status.setStyleSheet("background: #064e3b; color: #34d399; border: 1px solid #059669; border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11px;")
        else:
            self.lbl_status.setText(f"[{now_str}] ❌ {msg}")
            self.lbl_status.setStyleSheet("background: #450a0a; color: #f87171; border: 1px solid #dc2626; border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11px;")

        if hasattr(self, "btn_test_url"):
            self.btn_test_url.setEnabled(True)
            self.btn_test_url.setText("Ping Status")

    def reject(self) -> None:
        self._stop_ping_thread()
        super().reject()

    def closeEvent(self, event: object) -> None:
        self._stop_ping_thread()
        super().closeEvent(event)

    def close(self) -> bool:
        self._stop_ping_thread()
        return super().close()

    def _stop_ping_thread(self) -> None:
        if self._ping_worker:
            self._ping_worker.cancel()
            try:
                self._ping_worker.finished.disconnect()
            except Exception:
                pass
        if self._ping_thread and self._ping_thread.isRunning():
            self._ping_thread.quit()
            self._ping_thread.wait(600)
        self._ping_thread = None
        self._ping_worker = None

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
        self.config.confirm_disconnect = self.chk_confirm_disconnect.isChecked()

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
