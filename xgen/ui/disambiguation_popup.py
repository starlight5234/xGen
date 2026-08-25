"""
Overlapping Element Disambiguation Popup Menu.
"""

from __future__ import annotations

from typing import List, Optional
from PyQt6.QtCore import QPoint, pyqtSignal
from PyQt6.QtWidgets import QMenu, QWidget

from xgen.core.tree_parser import UINode


class DisambiguationPopup(QMenu):
    """Context menu allowing user to pick an element from overlapping candidates."""
    node_chosen = pyqtSignal(object)  # UINode

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(
            "QMenu { background: #14171e; color: #cbd5e1; border: 1px solid #232834; border-radius: 6px; padding: 4px; font-family: 'Segoe UI', system-ui, sans-serif; }"
            "QMenu::item { padding: 6px 16px; font-size: 11px; border-radius: 4px; }"
            "QMenu::item:selected { background: #2563eb; color: #ffffff; }"
        )

    def show_for_nodes(self, nodes: List[UINode], pos: QPoint) -> None:
        """Display menu actions for each overlapping node."""
        self.clear()
        if not nodes:
            return

        for node in nodes:
            name_str = f'"{node.name}"' if node.name else ""
            id_str = f"[{node.automation_id}]" if node.automation_id else ""
            action_text = f"{node.tag} {name_str} {id_str}".strip()

            action = self.addAction(action_text)
            action.triggered.connect(lambda checked, n=node: self.node_chosen.emit(n))

        self.popup(pos)
