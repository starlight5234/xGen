"""
xGen Global Modern Dark Theme & Dialog Styling System.
Provides unified dark palette, global stylesheets, high-contrast QMessageBox, and error formatting.
"""

from __future__ import annotations

import html
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget

GLOBAL_DARK_STYLESHEET = """
/* === Universal Window & Dialog Defaults === */
QMainWindow, QDialog, QMessageBox {
    background-color: #0f1115;
    color: #f1f5f9;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 11px;
}

/* === QMessageBox Deep Styling === */
QMessageBox {
    background-color: #0f1115;
    border: 1px solid #232834;
    border-radius: 8px;
}

QMessageBox QLabel {
    color: #f1f5f9;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.4;
    background-color: transparent;
    padding: 4px;
    min-height: 36px;
}

QMessageBox QPushButton {
    background-color: #1e2430;
    color: #f1f5f9;
    border: 1px solid #2e384d;
    border-radius: 6px;
    padding: 6px 20px;
    font-size: 11px;
    font-weight: 600;
    min-width: 68px;
    min-height: 18px;
}

QMessageBox QPushButton:hover {
    background-color: #2b3548;
    color: #ffffff;
    border-color: #3b82f6;
}

QMessageBox QPushButton:focus {
    border: 1px solid #3b82f6;
    background-color: #1d4ed8;
    color: #ffffff;
}

QMessageBox QPushButton:pressed {
    background-color: #1e40af;
}

/* === QToolTip Styling === */
QToolTip {
    background-color: #181c24;
    color: #f1f5f9;
    border: 1px solid #3b82f6;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 11px;
    font-weight: 500;
}

/* === QMenu / Context Menus === */
QMenu {
    background-color: #14171e;
    color: #cbd5e1;
    border: 1px solid #232834;
    border-radius: 6px;
    padding: 4px;
    font-size: 11px;
}

QMenu::item {
    padding: 6px 22px 6px 12px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}

QMenu::item:disabled {
    color: #475569;
}

QMenu::separator {
    height: 1px;
    background: #232834;
    margin: 4px 4px;
}

/* === Global Modern ScrollBars === */
QScrollBar:vertical {
    background: #0f1115;
    width: 8px;
    margin: 0;
    border: none;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #262b36;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #3b82f6;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    border: none;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: #0f1115;
    height: 8px;
    margin: 0;
    border: none;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #262b36;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #3b82f6;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    border: none;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* === QGroupBox Card Styling === */
QGroupBox {
    background-color: #14171e;
    border: 1px solid #232834;
    border-radius: 8px;
    margin-top: 12px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
    color: #93c5fd;
    font-size: 11px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: #0f1115;
    color: #93c5fd;
    font-weight: 600;
}

/* === CheckBoxes & RadioButtons Default Styling === */
QCheckBox, QRadioButton {
    color: #cbd5e1;
    font-size: 11px;
    spacing: 6px;
}

QCheckBox:hover, QRadioButton:hover {
    color: #ffffff;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #334155;
    background: #181c24;
}

QCheckBox::indicator:hover {
    border-color: #3b82f6;
}

QCheckBox::indicator:checked {
    background: #2563eb;
    border-color: #3b82f6;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #475569;
    background: #181c24;
}

QRadioButton::indicator:hover {
    border-color: #3b82f6;
}

QRadioButton::indicator:checked {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 1px solid #3b82f6;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #3b82f6, stop:0.55 #3b82f6, stop:0.6 #181c24, stop:1.0 #181c24);
}

/* === QLineEdit Base Styling === */
QLineEdit {
    background-color: #181c24;
    color: #f1f5f9;
    border: 1px solid #2a3140;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}

QLineEdit:focus {
    border-color: #3b82f6;
}

QLineEdit:disabled {
    background-color: #111317;
    color: #475569;
    border-color: #1e222b;
}

/* === QComboBox Universal Dropdown & Popup List Styling === */
QComboBox {
    background-color: #181c24;
    color: #f1f5f9;
    border: 1px solid #2a3140;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
}

QComboBox:hover {
    border-color: #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 18px;
}

QComboBox QAbstractItemView {
    background-color: #14171e;
    color: #cbd5e1;
    border: 1px solid #28303f;
    border-radius: 6px;
    padding: 4px;
    outline: none;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 4px 10px;
    border-radius: 4px;
    border-bottom: 1px solid #1e2430;
    margin: 1px 0px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #1e2533;
    color: #ffffff;
}

QComboBox QAbstractItemView::item:selected {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 500;
}
"""


def get_app_icon() -> QIcon:
    """Returns the application QIcon from SVG resources."""
    import sys
    from pathlib import Path

    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
        candidates.append(base_dir / "xgen" / "resources" / "xgen_app_icon.svg")
        candidates.append(base_dir / "xgen_app_icon.svg")

    theme_dir = Path(__file__).resolve().parent
    pkg_dir = theme_dir.parent
    candidates.append(pkg_dir / "resources" / "xgen_app_icon.svg")
    candidates.append(pkg_dir.parent / "xgen_app_icon.svg")

    for path in candidates:
        if path.exists():
            return QIcon(str(path))

    return QIcon()


def apply_dark_theme(app: QApplication) -> None:
    """
    Applies the global dark theme palette, stylesheet, and app icon to the QApplication.
    Ensures standard Qt widgets and native dialogs render with high-contrast dark aesthetics.
    """
    # 1. Configure Dark Palette
    palette = QPalette()
    dark_window = QColor(15, 17, 21)        # #0f1115
    dark_panel = QColor(20, 23, 30)         # #14171e
    dark_base = QColor(18, 21, 27)          # #12151b
    text_white = QColor(241, 245, 249)      # #f1f5f9
    text_dim = QColor(148, 163, 184)        # #94a3b8
    text_disabled = QColor(71, 85, 105)     # #475569
    accent_blue = QColor(37, 99, 235)       # #2563eb
    highlight_text = QColor(255, 255, 255)

    palette.setColor(QPalette.ColorRole.Window, dark_window)
    palette.setColor(QPalette.ColorRole.WindowText, text_white)
    palette.setColor(QPalette.ColorRole.Base, dark_base)
    palette.setColor(QPalette.ColorRole.AlternateBase, dark_panel)
    palette.setColor(QPalette.ColorRole.ToolTipBase, dark_panel)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_white)
    palette.setColor(QPalette.ColorRole.Text, text_white)
    palette.setColor(QPalette.ColorRole.Button, dark_panel)
    palette.setColor(QPalette.ColorRole.ButtonText, text_white)
    palette.setColor(QPalette.ColorRole.Highlight, accent_blue)
    palette.setColor(QPalette.ColorRole.HighlightedText, highlight_text)

    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_disabled)

    app.setPalette(palette)
    app.setStyleSheet(GLOBAL_DARK_STYLESHEET)

    # 2. Set Global Application Window Icon
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)


def format_session_error(err: str) -> tuple[str, str, str]:
    """
    Translates raw socket/driver connection exceptions into clear, actionable, friendly instructions.
    Returns: (title, friendly_message, technical_details)
    """
    err_str = str(err)
    if "10061" in err_str or "actively refused" in err_str or "Connection refused" in err_str:
        title = "Appium Connection Refused"
        msg = (
            "<b>Could not connect to Appium / WinAppDriver on port 4723.</b><br><br>"
            "Please ensure the automation driver server is started on this machine:<br><br>"
            "&nbsp;&nbsp;▶ Open Command Prompt / Terminal and run: <code style='color:#38bdf8; background:#181c24; padding:2px 6px; border-radius:4px;'>appium</code><br>"
            "&nbsp;&nbsp;▶ Or launch <code style='color:#38bdf8; background:#181c24; padding:2px 6px; border-radius:4px;'>WinAppDriver.exe</code> as Administrator.<br><br>"
            "Once running, click <b>Connect Session</b> again."
        )
        return title, msg, err_str

    if "Max retries exceeded" in err_str or "timed out" in err_str.lower() or "timeout" in err_str.lower():
        title = "Connection Timed Out"
        msg = (
            "<b>Communication with Appium timed out.</b><br><br>"
            "The driver server at <code style='color:#38bdf8;'>http://127.0.0.1:4723</code> did not respond.<br>"
            "Please verify that Appium is still active and not hanging."
        )
        return title, msg, err_str

    if "404" in err_str or "unknown command" in err_str.lower():
        title = "Appium Session Error"
        msg = (
            "<b>Appium server returned 404 / Unknown Command.</b><br><br>"
            "Ensure the Appium Windows Driver is installed:<br>"
            "&nbsp;&nbsp;<code>appium driver install --source=npm appium-windows-driver</code>"
        )
        return title, msg, err_str

    title = "Session Error"
    msg = f"<b>Failed to establish Appium session:</b><br><br>{html.escape(err_str[:300])}"
    return title, msg, err_str


def show_styled_message_box(
    parent: Optional[QWidget],
    title: str,
    text: str,
    icon: QMessageBox.Icon = QMessageBox.Icon.Warning,
    detailed_text: str = ""
) -> None:
    """
    Presents a styled, dark-mode QMessageBox with clear contrast and optional technical details.
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(f"xGen — {title}")
    msg_box.setText(text)
    msg_box.setTextFormat(Qt.TextFormat.RichText)
    msg_box.setIcon(icon)

    if detailed_text:
        msg_box.setDetailedText(detailed_text)

    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.setStyleSheet(GLOBAL_DARK_STYLESHEET)
    msg_box.exec()
