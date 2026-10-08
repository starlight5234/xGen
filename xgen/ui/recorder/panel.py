"""
Recorder Panel UI.
Timeline list, step detail view, candidate locator selector with state badges,
step notes editor, and export dialog integration.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional, Tuple
from PyQt6.QtCore import QEvent, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QVBoxLayout, QWidget, QApplication
)

from xgen.recorder.api import RecorderApi
from xgen.recorder.models import ActionType, LocatorCandidate, LocatorState, Step
from xgen.ui.recorder.bridge import RecorderQtBridge

logger = logging.getLogger("xgen.ui.recorder.panel")


class StepListItemWidget(QWidget):
    """Custom widget rendered for each step in the timeline."""
    def __init__(self, step: Step, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.step = step
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Seq badge
        lbl_seq = QLabel(f"#{self.step.seq}", self)
        lbl_seq.setStyleSheet("""
            background: #1e293b;
            color: #94a3b8;
            border-radius: 4px;
            padding: 2px 6px;
            font-weight: 600;
            font-size: 11px;
        """)

        # Action Verb & Icon
        icon_map = {
            ActionType.CLICK: "🖱️ Click",
            ActionType.DOUBLE_CLICK: "🖱️🖱️ DblClick",
            ActionType.RIGHT_CLICK: "🖱️ RightClick",
            ActionType.TYPE: "⌨️ Type",
            ActionType.KEY_PRESS: "⚡ Key",
            ActionType.SCROLL: "📜 Scroll",
            ActionType.SWITCH_WINDOW: "🪟 Switch",
            ActionType.WAIT: "⏳ Wait",
            ActionType.ASSERT: "🔍 Assert",
        }
        action_text = icon_map.get(self.step.action, self.step.action.value)
        lbl_action = QLabel(action_text, self)
        lbl_action.setStyleSheet("font-weight: 600; color: #38bdf8;")

        # Target description / XPath
        target_desc = ""
        if self.step.locators:
            idx = self.step.selected_locator if (self.step.selected_locator is not None and 0 <= self.step.selected_locator < len(self.step.locators)) else 0
            target_desc = self.step.locators[idx].xpath
        elif self.step.action == ActionType.TYPE:
            target_desc = f'"{self.step.params.get("text", "")}"'
        elif self.step.window and self.step.window.title:
            target_desc = self.step.window.title
        else:
            pt = self.step.params.get("point", {})
            target_desc = f"({pt.get('x', 0)}, {pt.get('y', 0)})"

        if self.step.action == ActionType.KEY_PRESS:
            keys_str = "+".join(self.step.params.get("keys", []))
            if keys_str:
                target_desc = f"[{keys_str}] {target_desc}".strip()

        lbl_target = QLabel(target_desc, self)
        lbl_target.setStyleSheet("color: #cbd5e1; font-family: Consolas, monospace; font-size: 11px;")
        lbl_target.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        layout.addWidget(lbl_seq)
        layout.addWidget(lbl_action)
        layout.addWidget(lbl_target, 1)


class LocatorComboBox(QComboBox):
    """
    ComboBox specialized for displaying long XPath locators.
    Constrains the popup dropdown width to match the combobox and parent card
    so it does not overflow across the screen or float detached, enables middle elision,
    and formats items with full XPath tooltips.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMaxVisibleItems(8)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)
        if self.view():
            self.view().setTextElideMode(Qt.TextElideMode.ElideMiddle)

    def showPopup(self) -> None:
        super().showPopup()
        popup = self.view().window()
        if popup:
            pos = self.mapToGlobal(self.rect().bottomLeft())
            target_width = self.width()
            screen = self.screen()
            if screen:
                screen_geom = screen.availableGeometry()
                if pos.x() + target_width > screen_geom.right():
                    target_width = max(200, screen_geom.right() - pos.x() - 10)
            popup.setFixedWidth(target_width)
            popup.move(pos.x(), pos.y() + 2)


class RecorderPanel(QWidget):
    """
    Timeline and Step Inspector Panel for automation recording.
    """
    def __init__(self, api: RecorderApi, bridge: RecorderQtBridge, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.api = api
        self.bridge = bridge
        self._current_step_id: Optional[str] = None
        self._steps: List[Step] = []
        self._deleted_steps_cache: List[Tuple[Step, int]] = []
        self._is_restoring_step: bool = False

        self._init_ui()
        self._wire_bridge()
        self._load_steps()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Header Title and Action Bar
        header = QHBoxLayout()
        self.lbl_title = QLabel("Recorded Steps Timeline", self)
        self.lbl_title.setStyleSheet("font-weight: 700; font-size: 14px; color: #f1f5f9;")
        header.addWidget(self.lbl_title)
        header.addStretch(1)

        self.btn_export = QPushButton("📤 Export...", self)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export_clicked)

        self.btn_clear = QPushButton("🗑 Clear", self)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._on_clear_clicked)

        header.addWidget(self.btn_export)
        header.addWidget(self.btn_clear)
        main_layout.addLayout(header)

        # Main Horizontal Splitter: Timeline List on Left, Detail on Right
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setHandleWidth(2)

        # Left: Timeline list
        self.step_list = QListWidget(self)
        self.step_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.step_list.currentRowChanged.connect(self._on_step_selection_changed)
        self.step_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.step_list.customContextMenuRequested.connect(self._on_context_menu)
        self.step_list.installEventFilter(self)
        self.splitter.addWidget(self.step_list)

        # Right: Detail Card in a ScrollArea so action buttons are always accessible
        self.detail_container = QWidget()
        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(8, 8, 8, 8)
        detail_layout.setSpacing(8)

        # Step Summary Box
        self.box_summary = QGroupBox("Step Details", self.detail_container)
        sum_layout = QVBoxLayout(self.box_summary)
        self.lbl_step_info = QLabel("Select a recorded step to inspect locators and properties.", self)
        self.lbl_step_info.setWordWrap(True)
        sum_layout.addWidget(self.lbl_step_info)
        detail_layout.addWidget(self.box_summary)

        # Locators Selector Box
        self.box_locators = QGroupBox("Ranked Locators (XPath)", self.detail_container)
        loc_layout = QVBoxLayout(self.box_locators)
        self.combo_locators = LocatorComboBox(self.box_locators)
        self.combo_locators.currentIndexChanged.connect(self._on_locator_changed)
        self.lbl_locator_state = QLabel("", self)
        loc_layout.addWidget(self.combo_locators)
        loc_layout.addWidget(self.lbl_locator_state)
        detail_layout.addWidget(self.box_locators)

        # Step Notes Box
        self.box_notes = QGroupBox("Notes & Description", self.detail_container)
        notes_layout = QHBoxLayout(self.box_notes)
        self.txt_notes = QLineEdit(self)
        self.txt_notes.setPlaceholderText("Add documentation or validation note for this step...")
        btn_save_note = QPushButton("Save", self)
        btn_save_note.clicked.connect(self._on_save_notes)
        notes_layout.addWidget(self.txt_notes, 1)
        notes_layout.addWidget(btn_save_note)
        detail_layout.addWidget(self.box_notes)

        # Step Actions Bar: [↩️ Undo] [💾 Save] [🗑️ Delete Step]
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        # 1. Undo Delete Button (Restores cached deleted step)
        self.btn_undo = QPushButton("↩️ Undo", self)
        self.btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_undo.setEnabled(False)
        self.btn_undo.setToolTip("No deleted steps to restore (Ctrl+Z)")
        self.btn_undo.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #0284c7;
                color: #ffffff;
            }
            QPushButton:disabled {
                background: #111827;
                color: #4b5563;
                border-color: #1f2937;
            }
        """)
        self.btn_undo.clicked.connect(self._on_undo_clicked)

        # 2. Save Step Changes Button
        self.btn_save = QPushButton("💾 Save", self)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip("Save step notes and selected locator changes (Ctrl+S)")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #a78bfa;
                border: 1px solid #7c3aed;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #7c3aed;
                color: #ffffff;
            }
            QPushButton:disabled {
                background: #111827;
                color: #4b5563;
                border-color: #1f2937;
            }
        """)
        self.btn_save.clicked.connect(self._on_save_step_clicked)

        # 3. Delete Step Button
        self.btn_delete_step = QPushButton("🗑️ Delete Step", self)
        self.btn_delete_step.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_step.setStyleSheet("""
            QPushButton {
                background: #7f1d1d;
                color: #fecaca;
                border: 1px solid #b91c1c;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #991b1b;
                color: #ffffff;
                border-color: #ef4444;
            }
            QPushButton:disabled {
                background: #111827;
                color: #4b5563;
                border-color: #1f2937;
            }
        """)
        self.btn_delete_step.clicked.connect(self._on_delete_step_clicked)

        btn_bar.addStretch(1)
        btn_bar.addWidget(self.btn_undo)
        btn_bar.addWidget(self.btn_save)
        btn_bar.addWidget(self.btn_delete_step)
        detail_layout.addLayout(btn_bar)

        detail_layout.addStretch(1)

        self.scroll_detail = QScrollArea(self)
        self.scroll_detail.setWidgetResizable(True)
        self.scroll_detail.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_detail.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_detail.setWidget(self.detail_container)
        self.splitter.addWidget(self.scroll_detail)

        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)
        main_layout.addWidget(self.splitter, 1)

        self._apply_theme()
        self._clear_detail()

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background: #0f172a;
                color: #e2e8f0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QListWidget {
                background: #141b2d;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item:selected {
                background: #1e293b;
                border-left: 3px solid #38bdf8;
            }
            QGroupBox {
                border: 1px solid #1e293b;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
                font-weight: 600;
                color: #94a3b8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 8px;
                color: #f1f5f9;
            }
            QComboBox {
                background: #181c24;
                color: #f1f5f9;
                border: 1px solid #2a3140;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #14171e;
                color: #cbd5e1;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: 1px solid #28303f;
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                min-height: 24px;
                padding: 4px 8px;
                border-radius: 4px;
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
            QPushButton {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #334155;
            }
        """)

    def _wire_bridge(self) -> None:
        self.bridge.step_added.connect(self._on_step_added)
        self.bridge.step_updated.connect(self._on_step_updated)
        self.bridge.step_removed.connect(self._on_step_removed)
        self.bridge.state_changed.connect(self._on_state_changed)

    def refresh_timeline(self) -> None:
        """Reloads steps from the active or latest recording session."""
        self._load_steps()

    def _load_steps(self) -> None:
        try:
            self._steps.clear()
            paged = self.api.get_steps(since_seq=0, limit=500)
            self._steps = list(paged.steps)
            self._rebuild_list()
            self._clear_detail()
            if self._steps:
                self.step_list.setCurrentRow(len(self._steps) - 1)
            if hasattr(self, "lbl_title"):
                count = len(self._steps)
                self.lbl_title.setText(f"Recorded Steps Timeline ({count} step{'s' if count != 1 else ''})")
        except Exception as e:
            logger.debug("Initial step load note: %s", e)

    def _rebuild_list(self) -> None:
        self.step_list.clear()
        for step in self._steps:
            item = QListWidgetItem()
            widget = StepListItemWidget(step)
            item.setSizeHint(widget.sizeHint())
            self.step_list.addItem(item)
            self.step_list.setItemWidget(item, widget)

    def _on_step_added(self, step: Step) -> None:
        if self._is_restoring_step:
            return

        # If this is the start of a new recording (#1) and we still have old steps, clear them
        if step.seq == 1 and len(self._steps) > 0:
            self._steps.clear()
            self.step_list.clear()
            self._clear_detail()

        self._steps.append(step)
        item = QListWidgetItem()
        widget = StepListItemWidget(step)
        item.setSizeHint(widget.sizeHint())
        self.step_list.addItem(item)
        self.step_list.setItemWidget(item, widget)
        self.step_list.scrollToBottom()

        if hasattr(self, "lbl_title"):
            count = len(self._steps)
            self.lbl_title.setText(f"Recorded Steps Timeline ({count} step{'s' if count != 1 else ''})")

    def _on_step_updated(self, step: Step) -> None:
        for i, s in enumerate(self._steps):
            if s.id == step.id:
                self._steps[i] = step
                item = self.step_list.item(i)
                if item:
                    widget = StepListItemWidget(step)
                    item.setSizeHint(widget.sizeHint())
                    self.step_list.setItemWidget(item, widget)
                if self._current_step_id == step.id:
                    typed_notes = self.txt_notes.text()
                    self._show_step_detail(step)
                    if typed_notes and not step.notes:
                        self.txt_notes.setText(typed_notes)
                break

    def _on_step_removed(self, step_id: str) -> None:
        removed_idx = -1
        for i, s in enumerate(self._steps):
            if s.id == step_id:
                removed_idx = i
                self._steps.pop(i)
                break

        if removed_idx >= 0:
            # Re-sequence remaining steps
            for idx, s in enumerate(self._steps):
                s.seq = idx + 1

            self._rebuild_list()

            if self._steps:
                new_row = min(removed_idx, len(self._steps) - 1)
                self.step_list.setCurrentRow(new_row)
            else:
                self._clear_detail()

        if hasattr(self, "lbl_title"):
            count = len(self._steps)
            self.lbl_title.setText(f"Recorded Steps Timeline ({count} step{'s' if count != 1 else ''})")

    def _on_state_changed(self, state: str) -> None:
        if state == "recording":
            # New recording session started: clear previous timeline items
            self._steps.clear()
            self._rebuild_list()
            self._clear_detail()
            if hasattr(self, "lbl_title"):
                self.lbl_title.setText("Recorded Steps Timeline (Recording...)")
        elif state == "idle":
            if hasattr(self, "lbl_title"):
                count = len(self._steps)
                self.lbl_title.setText(f"Recorded Steps Timeline ({count} step{'s' if count != 1 else ''})")

    def _on_step_selection_changed(self, row: int) -> None:
        if 0 <= row < len(self._steps):
            step = self._steps[row]
            self._current_step_id = step.id
            self._show_step_detail(step)
        else:
            self._clear_detail()

    def _show_step_detail(self, step: Step) -> None:
        win_title = step.window.title if step.window else "None"
        exe_name = step.process.exe_name if step.process else "Unknown"

        info_lines = [
            f"<b>Action:</b> {step.action.value.upper()} | <b>Seq:</b> #{step.seq}",
            f"<b>Created:</b> {step.created_at}",
            f"<b>Window:</b> {win_title}",
            f"<b>Process:</b> {exe_name} (PID: {step.process.pid if step.process else '?'})",
            f"<b>Parameters:</b> {json.dumps(step.params, ensure_ascii=False)}"
        ]
        self.lbl_step_info.setText("<br>".join(info_lines))

        # Populate locators dropdown
        self.combo_locators.blockSignals(True)
        self.combo_locators.clear()

        if step.action == ActionType.SWITCH_WINDOW:
            label = f"Target Window: {win_title}"
            self.combo_locators.addItem(label, 0)
            self.combo_locators.setItemData(0, label, Qt.ItemDataRole.ToolTipRole)
            self.lbl_locator_state.setText("Verification State: <b>N/A (Window Switch)</b>")
            self.combo_locators.setToolTip(label)
        elif step.locators:
            for idx, loc in enumerate(step.locators):
                score_str = f"Score: {loc.stability_score}" if loc.stability_score else ""
                label = f"{loc.xpath} ({score_str})" if score_str else loc.xpath
                self.combo_locators.addItem(label, idx)
                self.combo_locators.setItemData(idx, label, Qt.ItemDataRole.ToolTipRole)

            sel_idx = step.selected_locator if (step.selected_locator is not None and 0 <= step.selected_locator < len(step.locators)) else 0
            self.combo_locators.setCurrentIndex(sel_idx)

            active_loc = step.locators[sel_idx]
            self.lbl_locator_state.setText(f"Verification State: <b>{active_loc.state.value.upper()}</b>")
            self.combo_locators.setToolTip(f"Active XPath:\n{active_loc.xpath}")
        else:
            self.combo_locators.addItem("(No locators synthesized)", -1)
            self.combo_locators.setItemData(0, "(No locators synthesized)", Qt.ItemDataRole.ToolTipRole)
            self.lbl_locator_state.setText("Verification State: <b>UNRESOLVED</b>")
            self.combo_locators.setToolTip("No locators synthesized for this step.")

        self.combo_locators.blockSignals(False)

        # Notes
        self.txt_notes.setText(step.notes)
        self.btn_save.setEnabled(True)
        self.btn_delete_step.setEnabled(True)

    def _clear_detail(self) -> None:
        self._current_step_id = None
        self.lbl_step_info.setText("Select a recorded step to inspect locators and properties.")
        self.combo_locators.clear()
        self.lbl_locator_state.setText("")
        self.txt_notes.clear()
        self.btn_save.setEnabled(False)
        self.btn_delete_step.setEnabled(False)

    def _on_locator_changed(self, index: int) -> None:
        if self._current_step_id and index >= 0:
            try:
                self.api.select_locator(self._current_step_id, index)
                # Update tooltip for current selection
                item_tip = self.combo_locators.itemData(index, Qt.ItemDataRole.ToolTipRole)
                if item_tip:
                    self.combo_locators.setToolTip(f"Active XPath:\n{item_tip}")
            except Exception as e:
                logger.debug("Failed to update selected locator: %s", e)

    def _on_save_notes(self) -> None:
        self._on_save_step_clicked()

    def _on_save_step_clicked(self) -> None:
        if not self._current_step_id:
            return

        try:
            # 1. Update notes
            notes_text = self.txt_notes.text().strip()
            try:
                self.api.update_step(self._current_step_id, {"notes": notes_text})
            except Exception as err:
                logger.debug("API step update note: %s", err)

            # 2. Update selected locator if valid
            loc_idx = self.combo_locators.currentIndex()
            if loc_idx >= 0:
                try:
                    self.api.select_locator(self._current_step_id, loc_idx)
                except Exception as err:
                    logger.debug("API select locator note: %s", err)

            # 3. Update in-memory step object
            for s in self._steps:
                if s.id == self._current_step_id:
                    s.notes = notes_text
                    if 0 <= loc_idx < len(s.locators):
                        s.selected_locator = loc_idx
                    break

            # 4. Visual feedback
            self._flash_saved_feedback()
        except Exception as e:
            logger.debug("Could not save changes: %s", e)

    def _flash_saved_feedback(self) -> None:
        self.btn_save.setText("✅ Saved!")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #065f46;
                color: #6ee7b7;
                border: 1px solid #10b981;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
        """)
        QTimer.singleShot(1400, self._reset_save_button)

    def _reset_save_button(self) -> None:
        self.btn_save.setText("💾 Save")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #a78bfa;
                border: 1px solid #7c3aed;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #7c3aed;
                color: #ffffff;
            }
            QPushButton:disabled {
                background: #111827;
                color: #4b5563;
                border-color: #1f2937;
            }
        """)

    def _on_delete_step_clicked(self) -> None:
        step_id = self._current_step_id
        if not step_id:
            row = self.step_list.currentRow()
            if 0 <= row < len(self._steps):
                step_id = self._steps[row].id

        if not step_id:
            QMessageBox.information(self, "Delete Step", "Please select a step in the timeline to delete.")
            return

        # Cache step and original position before deleting for undo
        deleted_step: Optional[Step] = None
        deleted_idx = -1
        for i, s in enumerate(self._steps):
            if s.id == step_id:
                deleted_step = s
                deleted_idx = i
                break

        try:
            ok = self.api.delete_step(step_id)
            if deleted_step is not None:
                self._deleted_steps_cache.append((deleted_step, deleted_idx))
                self._update_undo_button_state()
            self._on_step_removed(step_id)
        except Exception as e:
            QMessageBox.warning(self, "Delete Step", f"Could not delete step: {e}")

    def _on_undo_clicked(self) -> None:
        if not self._deleted_steps_cache:
            return

        step, orig_idx = self._deleted_steps_cache.pop()
        self._is_restoring_step = True
        try:
            if hasattr(self.api, "restore_step"):
                self.api.restore_step(step, orig_idx)

            insert_idx = min(orig_idx, len(self._steps)) if orig_idx >= 0 else len(self._steps)
            self._steps.insert(insert_idx, step)
            for i, s in enumerate(self._steps):
                s.seq = i + 1

            self._rebuild_list()
            self.step_list.setCurrentRow(insert_idx)
            self._show_step_detail(step)
            self._update_undo_button_state()

            if hasattr(self, "lbl_title"):
                count = len(self._steps)
                self.lbl_title.setText(f"Recorded Steps Timeline ({count} step{'s' if count != 1 else ''})")
        except Exception as e:
            logger.debug("Failed restoring step via undo: %s", e)
            QMessageBox.warning(self, "Undo", f"Could not restore step: {e}")
        finally:
            self._is_restoring_step = False

    def _update_undo_button_state(self) -> None:
        has_undo = len(self._deleted_steps_cache) > 0
        self.btn_undo.setEnabled(has_undo)
        if has_undo:
            last_step, _ = self._deleted_steps_cache[-1]
            act = last_step.action.value.upper() if hasattr(last_step.action, "value") else str(last_step.action)
            count = len(self._deleted_steps_cache)
            self.btn_undo.setToolTip(f"Undo delete: Restore Step #{last_step.seq} ({act})\nShortcut: Ctrl+Z")
            self.btn_undo.setText(f"↩️ Undo ({count})" if count > 1 else "↩️ Undo")
        else:
            self.btn_undo.setToolTip("No deleted steps to restore (Ctrl+Z)")
            self.btn_undo.setText("↩️ Undo")

    def _on_context_menu(self, pos) -> None:
        item = self.step_list.itemAt(pos)
        if not item:
            return
        row = self.step_list.row(item)
        if 0 <= row < len(self._steps):
            self.step_list.setCurrentRow(row)
            menu = QMenu(self)
            action_save = menu.addAction("💾 Save Step (Ctrl+S)")
            action_del = menu.addAction("🗑️ Delete Step (Del)")
            action_undo = None
            if self._deleted_steps_cache:
                menu.addSeparator()
                count = len(self._deleted_steps_cache)
                action_undo = menu.addAction(f"↩️ Undo Delete ({count}) (Ctrl+Z)")

            action = menu.exec(self.step_list.mapToGlobal(pos))
            if action == action_del:
                self._on_delete_step_clicked()
            elif action == action_save:
                self._on_save_step_clicked()
            elif action_undo and action == action_undo:
                self._on_undo_clicked()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.step_list and event.type() == QEvent.Type.KeyPress:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_Z:
                    self._on_undo_clicked()
                    return True
                elif event.key() == Qt.Key.Key_S:
                    self._on_save_step_clicked()
                    return True
            elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._on_delete_step_clicked()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Z:
                self._on_undo_clicked()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_S:
                self._on_save_step_clicked()
                event.accept()
                return
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._on_delete_step_clicked()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_clear_clicked(self) -> None:
        reply = QMessageBox.question(
            self, "Clear Timeline", "Are you sure you want to clear all recorded steps?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Cache all steps for undo in case of accidental clear
            for s in reversed(self._steps):
                self._deleted_steps_cache.append((s, s.seq - 1))
            self._update_undo_button_state()

            try:
                if hasattr(self.api, "clear_steps"):
                    self.api.clear_steps()
                else:
                    for s in list(self._steps):
                        self.api.delete_step(s.id)
            except Exception as e:
                logger.debug("Failed clearing steps via api: %s", e)
            self._steps.clear()
            self._rebuild_list()
            self._clear_detail()
            if hasattr(self, "lbl_title"):
                self.lbl_title.setText("Recorded Steps Timeline (0 steps)")

    def _on_export_clicked(self) -> None:
        status = self.api.status()
        rec_id = status.recording_id
        if not rec_id:
            recs = self.api.list_recordings()
            if recs:
                rec_id = recs[0].id
            else:
                QMessageBox.information(self, "Export", "No recordings available to export.")
                return

        # Simple prompt for format
        exporter_id = "action_xpath_json"
        try:
            result = self.api.export(rec_id, exporter_id=exporter_id)
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Export failed: {e}")
            return

        # Save to file or copy
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Action-XPath JSON", result.filename, "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(result.text)
            QMessageBox.information(self, "Export Complete", f"Saved export to:\n{file_path}")
        else:
            QApplication.clipboard().setText(result.text)
            QMessageBox.information(self, "Copied to Clipboard", "Exported script copied to system clipboard.")
