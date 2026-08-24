"""
xGen — Main Application Entry Point
"""

from __future__ import annotations

import logging
import sys
from PyQt6.QtWidgets import QApplication, QMessageBox

# 1. Initialize Windows Per-Monitor DPI awareness before any UI creation
from xgen.utils.dpi import init_dpi_awareness
init_dpi_awareness()

from xgen.config import ConfigManager
from xgen.ui.crash_dialog import install_global_excepthook
from xgen.ui.main_window import MainWindow
from xgen.utils.logger import setup_logging

# Setup rotating log and install crash boundary
log_file = setup_logging(logging.INFO)
install_global_excepthook()

logger = logging.getLogger("xgen.main")


def main() -> int:
    logger.info("Starting xGen (Log: %s)...", log_file)
    app = QApplication(sys.argv)
    app.setApplicationName("xGen")
    app.setOrganizationName("xGen Automation")

    # Load configuration
    config = ConfigManager.load()

    # Create and show Main Window
    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
