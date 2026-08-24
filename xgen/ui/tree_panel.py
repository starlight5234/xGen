"""
Lazy Virtual Tree Panel (Left Panel).
Renders UINode tree with on-demand expansion, search filtering, and transient node badges.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xgen.core.tree_parser import UINode

logger = logging.getLogger("xgen.tree_panel")


class TreePanel(QWidget):
    """
    Left-hand panel rendering hierarchical UI tree with search and selection.
    """
    node_selected = pyqtSignal(object)  # UINode

    # ControlType emoji/icon map
    TYPE_ICONS: Dict[str, str] = {
        "Window": "🪟",
        "Pane": "📦",
        "Group": "📁",
        "Button": "🔘",
        "Edit": "✏️",
        "Text": "📝",
        "Menu": "📋",
        "MenuItem": "🔹",
        "List": "📜",
        "ListItem": "▫️",
        "Tree": "🌲",
        "TreeItem": "🌿",
        "ComboBox": "🔽",
        "CheckBox": "☑️",
        "RadioButton": "🔘",
        "Tab": "📑",
        "TabItem": "📄",
        "ToolBar": "🛠️",
        "StatusBar": "📊",
        "ToolTip": "💬",
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_root: Optional[UINode] = None
        self._node_item_map: Dict[int, QTreeWidgetItem] = {}  # id(node) -> item
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet("TreePanel { background: #12151b; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 1. Search Filter Bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Filter elements (Name, ID, Class)...")
        self.search_edit.setStyleSheet(
            "QLineEdit { background: #181c24; color: #f1f5f9; border: 1px solid #2a3140; border-radius: 6px; padding: 6px 10px; font-size: 11px; }"
            "QLineEdit:focus { border-color: #3b82f6; }"
        )
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._perform_search)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())

        btn_clear = QPushButton("✕")
        btn_clear.setMaximumWidth(24)
        btn_clear.setToolTip("Clear search filter")
        btn_clear.setStyleSheet("QPushButton { background: transparent; color: #64748b; border: none; font-weight: bold; font-size: 11px; } QPushButton:hover { color: #f1f5f9; }")
        btn_clear.clicked.connect(self.search_edit.clear)

        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(btn_clear)
        layout.addLayout(search_layout)

        # 2. Main QTreeWidget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setIndentation(16)
        self.tree_widget.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree_widget.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setStyleSheet(
            "QTreeWidget { background: #15181f; color: #cbd5e1; border: 1px solid #222733; border-radius: 6px; font-size: 11px; padding: 4px; }"
            "QTreeWidget::item { height: 24px; padding: 2px 4px; border-radius: 4px; }"
            "QTreeWidget::item:hover { background: #1e2430; color: #ffffff; }"
            "QTreeWidget::item:selected { background: #1e3a8a; color: #93c5fd; font-weight: 600; }"
            "QScrollBar:horizontal { border: none; background: #12151b; height: 10px; margin: 0px; border-radius: 4px; }"
            "QScrollBar::handle:horizontal { background: #2a3140; min-width: 24px; border-radius: 4px; }"
            "QScrollBar::handle:horizontal:hover { background: #3b82f6; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { border: none; background: none; width: 0px; }"
            "QScrollBar:vertical { border: none; background: #12151b; width: 10px; margin: 0px; border-radius: 4px; }"
            "QScrollBar::handle:vertical { background: #2a3140; min-height: 24px; border-radius: 4px; }"
            "QScrollBar::handle:vertical:hover { background: #3b82f6; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; background: none; height: 0px; }"
        )
        self.tree_widget.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree_widget.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self.tree_widget)

    def populate(self, root: UINode) -> None:
        """Populate tree with on-demand lazy expansion."""
        self._current_root = root
        self._node_item_map.clear()
        self.tree_widget.clear()

        if root is None:
            return

        # Add top root item
        root_item = self._create_tree_item(root)
        self.tree_widget.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def add_transient_nodes(self, transient_root: UINode) -> None:
        """Append or update transient subtree (e.g. from F4 Freeze snapshot) in the tree view."""
        if not self._current_root or not transient_root:
            return

        # If user pressed F4 over the root container itself, don't duplicate the root
        if self._current_root and transient_root.tag == self._current_root.tag and transient_root.name == self._current_root.name:
            if id(self._current_root) in self._node_item_map:
                self.tree_widget.setCurrentItem(self._node_item_map[id(self._current_root)])
            return

        # Check if this transient node was already added
        if id(transient_root) in self._node_item_map:
            item = self._node_item_map[id(transient_root)]
            self.tree_widget.setCurrentItem(item)
            return

        # Deduplicate: Replace any previous transient top-level item with matching name/tag
        for i in range(self.tree_widget.topLevelItemCount() - 1, 0, -1):
            top_item = self.tree_widget.topLevelItem(i)
            node_data = top_item.data(0, Qt.ItemDataRole.UserRole)
            if node_data and getattr(node_data, "is_transient", False):
                if node_data.name == transient_root.name and node_data.tag == transient_root.tag:
                    self.tree_widget.takeTopLevelItem(i)

        item = self._create_tree_item(transient_root)
        self.tree_widget.addTopLevelItem(item)
        item.setExpanded(True)
        self.tree_widget.setCurrentItem(item)

    def select_node(self, node: UINode) -> None:
        """Expand path to node and highlight/select it in the tree."""
        self.expand_to_node(node)

    def expand_to_node(self, node: UINode) -> None:
        """Expand path to node and select it in the tree."""
        if not node:
            return

        # Collect path from node up to root
        path: List[UINode] = []
        curr: Optional[UINode] = node
        while curr:
            path.append(curr)
            curr = curr.parent
        path.reverse()

        # Traverse and expand along path
        parent_item: Optional[QTreeWidgetItem] = None
        for step_node in path:
            item = self._node_item_map.get(id(step_node))
            if not item and parent_item:
                # Ensure children of parent are loaded
                self._load_children_if_needed(parent_item, step_node.parent)
                item = self._node_item_map.get(id(step_node))

            if item:
                item.setExpanded(True)
                parent_item = item

        # Select target item
        target_item = self._node_item_map.get(id(node))
        if target_item:
            self.tree_widget.blockSignals(True)
            self.tree_widget.setCurrentItem(target_item)
            self.tree_widget.resizeColumnToContents(0)
            self.tree_widget.scrollToItem(target_item)
            self.tree_widget.blockSignals(False)

    def _create_tree_item(self, node: UINode) -> QTreeWidgetItem:
        icon = self.TYPE_ICONS.get(node.tag, "🔹")
        if node.is_transient:
            icon = f"⚡ {icon}"

        label = f"{icon} {node.display_label()}"
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        self._node_item_map[id(node)] = item

        if node.is_transient:
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)
            item.setForeground(0, QColor(255, 179, 0))  # amber

        # If has children, add dummy placeholder child for lazy loading
        if node.children:
            dummy = QTreeWidgetItem(["Loading..."])
            item.addChild(dummy)

        return item

    def _load_children_if_needed(self, parent_item: QTreeWidgetItem, node: Optional[UINode]) -> None:
        if not node or not node.children:
            return

        # Check if dummy item is present
        if parent_item.childCount() == 1 and parent_item.child(0).text(0) == "Loading...":
            parent_item.takeChild(0)  # remove dummy
            for child_node in node.children:
                child_item = self._create_tree_item(child_node)
                parent_item.addChild(child_item)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        node: Optional[UINode] = item.data(0, Qt.ItemDataRole.UserRole)
        if node:
            self._load_children_if_needed(item, node)
            self.tree_widget.resizeColumnToContents(0)

    def _on_tree_selection_changed(self) -> None:
        selected_items = self.tree_widget.selectedItems()
        if not selected_items:
            return
        node: Optional[UINode] = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if node:
            self.node_selected.emit(node)

    def _on_search_text_changed(self, query: str) -> None:
        self._search_timer.start()

    def _perform_search(self) -> None:
        q = self.search_edit.text().strip().lower()
        if not self._current_root:
            return

        self.tree_widget.setUpdatesEnabled(False)
        self.tree_widget.blockSignals(True)
        try:
            if not q:
                # Unhide all
                for item in self._node_item_map.values():
                    item.setHidden(False)
                return

            # 1. Search full in-memory UINode hierarchy (capped at 150 matches to keep UI ultra responsive)
            MAX_SEARCH_RESULTS = 150
            matching_nodes: List[UINode] = []
            matching_node_ids = set()

            def _search_rec(n: UINode) -> None:
                if len(matching_nodes) >= MAX_SEARCH_RESULTS:
                    return
                if (
                    q in n.name.lower()
                    or q in n.automation_id.lower()
                    or q in n.class_name.lower()
                    or q in n.tag.lower()
                ):
                    matching_nodes.append(n)
                    matching_node_ids.add(id(n))
                for child in n.children:
                    _search_rec(child)
                    if len(matching_nodes) >= MAX_SEARCH_RESULTS:
                        return

            _search_rec(self._current_root)

            # 2. For every match, ensure its full ancestor chain is instantiated in the tree
            ancestor_ids = set()
            for node in matching_nodes:
                curr = node.parent
                while curr:
                    ancestor_ids.add(id(curr))
                    curr = curr.parent
                self._ensure_path_loaded(node)

            # 3. Set visibility: show matches and their ancestors, hide others
            for node_id, item in self._node_item_map.items():
                if node_id in matching_node_ids or node_id in ancestor_ids:
                    item.setHidden(False)
                    if node_id in ancestor_ids:
                        item.setExpanded(True)
                else:
                    item.setHidden(True)
        finally:
            self.tree_widget.blockSignals(False)
            self.tree_widget.setUpdatesEnabled(True)

    def _ensure_path_loaded(self, node: UINode) -> None:
        """Ensure all ancestors of node have their children instantiated in the tree."""
        path: List[UINode] = []
        curr: Optional[UINode] = node
        while curr:
            path.append(curr)
            curr = curr.parent
        path.reverse()

        parent_item: Optional[QTreeWidgetItem] = None
        for step_node in path:
            item = self._node_item_map.get(id(step_node))
            if not item and parent_item and step_node.parent:
                self._load_children_if_needed(parent_item, step_node.parent)
                item = self._node_item_map.get(id(step_node))
            if item:
                parent_item = item
