"""
Element Attribute Panel (Collapsible Inspector).
Displays detailed key-value attribute inspection for the selected UINode.
Can be collapsed or expanded to maximize vertical space for XPath generation.
"""

from __future__ import annotations

import logging
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xgen.core.tree_parser import UINode

logger = logging.getLogger("xgen.attribute_panel")


class AttributePanel(QWidget):
    """Collapsible panel displaying element attributes table."""
    collapsed_toggled = pyqtSignal(bool)  # True if collapsed, False if expanded

    PRIORITY_KEYS = [
        "ControlType",
        "AutomationId",
        "Name",
        "ClassName",
        "IsEnabled",
        "IsOffscreen",
        "BoundingRectangle",
        "RuntimeId",
        "HelpText",
        "AriaProperties",
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_collapsed = False
        self._title_text = "Element Attributes"
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("AttributePanel { background: #12151b; border: 1px solid #1e222b; border-radius: 6px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Interactive Collapsible Header Bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.btn_toggle = QPushButton("▼")
        self.btn_toggle.setFixedSize(20, 20)
        self.btn_toggle.setToolTip("Collapse / Expand Element Attributes")
        self.btn_toggle.setStyleSheet(
            "QPushButton { background: #181c24; color: #94a3b8; border: 1px solid #28303f; border-radius: 4px; font-size: 10px; font-weight: bold; }"
            "QPushButton:hover { background: #222733; color: #f1f5f9; border-color: #3b82f6; }"
        )
        self.btn_toggle.clicked.connect(self.toggle_collapse)
        header_layout.addWidget(self.btn_toggle)

        self.lbl_title = QLabel("Element Attributes")
        self.lbl_title.setStyleSheet("color: #f1f5f9; font-weight: 600; font-size: 11px; padding: 2px 0;")
        self.lbl_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_title.mousePressEvent = lambda _: self.toggle_collapse()
        header_layout.addWidget(self.lbl_title)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 500;")
        header_layout.addWidget(self.lbl_count)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 2. Table Widget
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            "QTableWidget { background: #15181f; color: #f1f5f9; border: 1px solid #222733; border-radius: 6px; font-size: 11px; gridline-color: #1e222b; }"
            "QHeaderView { background: #1a1d24; border: none; border-bottom: 1px solid #222733; }"
            "QHeaderView::section { background: #1a1d24; color: #94a3b8; padding: 6px 8px; border: none; font-weight: 600; font-size: 10px; }"
            "QTableCornerButton::section { background: #1a1d24; border: none; }"
            "QTableWidget::item { padding: 4px 8px; }"
            "QTableWidget::item:hover { background: #1e2430; }"
            "QTableWidget::item:selected { background: #1e3a8a; color: #93c5fd; font-weight: 600; }"
        )
        layout.addWidget(self.table)

    def toggle_collapse(self) -> None:
        """Toggle attribute table visibility between expanded and collapsed."""
        self._is_collapsed = not self._is_collapsed
        self.table.setVisible(not self._is_collapsed)
        self.btn_toggle.setText("▶" if self._is_collapsed else "▼")
        if self._is_collapsed:
            self.setMaximumHeight(32)
            self.lbl_title.setText(f"{self._title_text} [Collapsed]")
        else:
            self.setMaximumHeight(16777215)
            self.lbl_title.setText(self._title_text)
        self.collapsed_toggled.emit(self._is_collapsed)

    def populate(self, node: Optional[UINode]) -> None:
        """Populate attributes table from UINode."""
        self.table.setRowCount(0)
        if not node:
            self._title_text = "Element Attributes"
            self.lbl_title.setText(self._title_text if not self._is_collapsed else f"{self._title_text} [Collapsed]")
            self.lbl_count.setText("")
            return

        self._title_text = f"Attributes: {node.tag} (depth {node.depth})"
        self.lbl_title.setText(self._title_text if not self._is_collapsed else f"{self._title_text} [Collapsed]")

        attrs = dict(node.attributes)

        # Gather priority attributes first in defined order
        ordered_rows = []
        for key in self.PRIORITY_KEYS:
            if key in attrs:
                val = attrs.pop(key)
                ordered_rows.append((key, val))

        # Append remaining attributes alphabetically
        for key in sorted(attrs.keys()):
            ordered_rows.append((key, attrs[key]))

        self.lbl_count.setText(f"({len(ordered_rows)} attributes)")
        self.table.setRowCount(len(ordered_rows))
        for row, (k, v) in enumerate(ordered_rows):
            item_k = QTableWidgetItem(k)
            item_k.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_k.setForeground(Qt.GlobalColor.lightGray)
            item_k.setToolTip(k)

            # Format formatted value
            val_display = str(v)
            if k == "BoundingRectangle" and node.bounding_rect:
                r = node.bounding_rect
                val_display = f"X={r.left}, Y={r.top}, W={r.width}, H={r.height}"

            item_v = QTableWidgetItem(val_display)
            item_v.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_v.setToolTip(val_display)

            # Highlight flags
            if k == "AutomationId" and str(v).isdigit():
                item_v.setText(f"⚠️ {val_display} (numeric WinForms ID)")
                item_v.setForeground(Qt.GlobalColor.yellow)
            elif k == "Name" and v:
                item_v.setText(f"{val_display}")

            self.table.setItem(row, 0, item_k)
            self.table.setItem(row, 1, item_v)

        self.table.resizeColumnsToContents()

    def clear(self) -> None:
        self.table.setRowCount(0)
        self._title_text = "Element Attributes"
        self.lbl_title.setText(self._title_text)
        self.lbl_count.setText("")
