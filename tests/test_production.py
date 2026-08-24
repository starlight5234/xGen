import sys
import tempfile
from pathlib import Path
from xgen.config import ConfigManager, XGenConfig
from xgen.utils.logger import setup_logging
from xgen.ui.crash_dialog import CrashDialog

def test_logger_setup():
    log_path = setup_logging()
    assert log_path.exists() or log_path.parent.exists()
    assert log_path.name == "xgen.log"

def test_crash_dialog_creation(qapp):
    try:
        raise ValueError("Simulated diagnostic error")
    except ValueError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        dialog = CrashDialog(exc_type, exc_val, exc_tb)
        assert "ValueError" in dialog.report_text
        assert "Simulated diagnostic error" in dialog.report_text

def test_window_geometry_persistence(test_dir: Path):
    cfg_file = test_dir / "config.json"
    cfg = XGenConfig(
        window_width=1400,
        window_height=900,
        window_x=100,
        window_y=150,
        window_maximized=True,
        splitter_sizes=[300, 350, 500],
        pin_on_top=True
    )
    ConfigManager.save(cfg, cfg_file)

    loaded = ConfigManager.load(cfg_file)
    assert loaded.window_width == 1400
    assert loaded.window_height == 900
    assert loaded.window_x == 100
    assert loaded.window_y == 150
    assert loaded.window_maximized is True
    assert loaded.splitter_sizes == [300, 350, 500]
    assert loaded.pin_on_top is True
