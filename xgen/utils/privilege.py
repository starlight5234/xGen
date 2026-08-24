"""
Windows Privilege & Elevation utilities.
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import sys

logger = logging.getLogger("xgen.privilege")


def is_running_as_admin() -> bool:
    """Return True if the current process is running with Administrator privileges."""
    if platform.system() != "Windows":
        return os.getuid() == 0 if hasattr(os, "getuid") else False

    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """
    Relaunch the current application elevated (UAC prompt).
    Returns True if ShellExecute was called, False on error.
    """
    if platform.system() != "Windows":
        return False

    if is_running_as_admin():
        logger.info("Already running with Administrator privileges.")
        return True

    try:
        # Re-launch with same arguments
        executable = sys.executable
        params = " ".join([f'"{arg}"' for arg in sys.argv])
        
        # ShellExecuteW with 'runas' verb triggers UAC elevation prompt
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            None,
            1  # SW_SHOWNORMAL
        )
        if ret > 32:
            logger.info("Relaunch as administrator initiated. Exiting current process.")
            sys.exit(0)
            return True
        else:
            logger.warning("ShellExecuteW failed with error code: %d", ret)
            return False
    except Exception as e:
        logger.error("Failed to relaunch as administrator: %s", e)
        return False
