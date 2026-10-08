"""
Tests for shared kernel Qt-decoupling and purity.
Validates that core XPath, caching, and parsing modules can be imported
and executed in a headless environment without importing PyQt6.
"""
import sys
import subprocess
import pytest

def test_kernel_modules_import_without_qt():
    """
    Spawns a clean Python subprocess to verify that importing core kernel modules
    does NOT import PyQt6 or any Qt libraries into sys.modules.
    """
    code = """
import sys

# Import core modules
from xgen.core.xpath_generator import XPathGenerator
from xgen.core.xpath_verifier import XPathVerifier
from xgen.core.tree_parser import TreeParser, UINode
from xgen.core.tree_cache import TreeCacheStore, WindowTreeCache
from xgen.core.stability_scorer import StabilityScorer
from xgen.core.volatility_classifier import VolatilityClassifier
from xgen.core.driver_dialect import active_dialect
from xgen.core.appium_compat import AppiumXPathCompatLayer
from xgen.utils.rect import Rect
from xgen.utils.xpath_escape import escape_xpath_literal

# Check that no Qt module was imported
qt_modules = [m for m in sys.modules if m.startswith("PyQt") or m.startswith("PySide")]
if qt_modules:
    print(f"FAILED: Qt modules found in sys.modules: {qt_modules}")
    sys.exit(1)

print("SUCCESS: Core kernel is completely Qt-free")
sys.exit(0)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"Kernel purity check failed:\nStdout: {result.stdout}\nStderr: {result.stderr}"
    assert "SUCCESS" in result.stdout

def test_rwlock_concurrency_and_exclusion():
    """
    Verifies that RWLock supports multiple concurrent readers and exclusive writers.
    """
    import threading
    import time
    from xgen.core.tree_cache import RWLock

    lock = RWLock()
    active_readers = 0
    max_concurrent_readers = 0
    writer_active = False
    errors = []

    def reader():
        nonlocal active_readers, max_concurrent_readers
        for _ in range(20):
            lock.lockForRead()
            try:
                if writer_active:
                    errors.append("Reader found writer active!")
                active_readers += 1
                if active_readers > max_concurrent_readers:
                    max_concurrent_readers = active_readers
                time.sleep(0.001)
            finally:
                active_readers -= 1
                lock.unlock()

    def writer():
        nonlocal writer_active
        for _ in range(10):
            lock.lockForWrite()
            try:
                writer_active = True
                if active_readers > 0:
                    errors.append("Writer found active readers!")
                time.sleep(0.002)
            finally:
                writer_active = False
                lock.unlock()

    threads = [threading.Thread(target=reader) for _ in range(5)] + [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrency errors encountered: {errors}"
    assert max_concurrent_readers > 1, f"Expected concurrent readers, max was {max_concurrent_readers}"
