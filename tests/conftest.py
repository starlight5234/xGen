import pytest
from PyQt6.QtWidgets import QApplication
from xgen.core.tree_parser import TreeParser

SAMPLE_XML = """<AppiumAUT>
  <Window Name='Main Window' AutomationId='win_main' ClassName='MainWnd'>
    <Pane Name='Container' AutomationId='pan_container'>
      <Button Name='Submit' AutomationId='btn_submit' ClassName='ButtonClass'/>
      <Button Name='Duplicate' ClassName='ButtonClass'/>
      <Button Name='Duplicate' ClassName='ButtonClass'/>
      <Edit Name='Username' AutomationId='1001' ClassName='EditClass'/>
      <Button Name='He said "Hello"' ClassName='ButtonClass'/>
    </Pane>
  </Window>
</AppiumAUT>"""

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def parsed_data():
    from lxml import etree
    root = TreeParser.parse(SAMPLE_XML)
    lxml_tree = etree.fromstring(SAMPLE_XML.encode())
    return root, lxml_tree

@pytest.fixture
def test_dir():
    """Isolated temporary directory inside workspace for test executions."""
    import os
    import time
    from pathlib import Path
    import shutil

    scratch_base = Path(__file__).resolve().parent.parent / ".pytest_scratch"
    d = scratch_base / f"t_{os.getpid()}_{int(time.time() * 1000)}"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
