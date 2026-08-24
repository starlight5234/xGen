"""
XPath Legend, Ranking Index, and Selector Guide Dialog.
Provides in-depth documentation on Stability Scores, Localization Risk, Tiers, and Badges.
"""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QAbstractItemView,
)


class LegendDialog(QDialog):
    """Interactive documentation dialog detailing xGen XPath generation heuristics and badges."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("xGen — XPath Guide & Index")
        self.resize(740, 580)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("""
            QDialog { background: #0f1115; color: #f1f5f9; font-family: 'Segoe UI', system-ui, sans-serif; }
            QTabWidget::pane { border: 1px solid #232834; background: #14171e; border-radius: 6px; }
            QTabBar::tab { background: #181c24; color: #94a3b8; padding: 8px 16px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-size: 11px; font-weight: 500; }
            QTabBar::tab:selected { background: #14171e; color: #60a5fa; font-weight: bold; border-top: 2px solid #3b82f6; }
            QTabBar::tab:hover:!selected { background: #1f242e; color: #e2e8f0; }
            QScrollArea { border: none; background: transparent; }
            QScrollArea > QWidget { background: transparent; }
            QScrollBar:vertical { background: #0f1115; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #262b36; min-height: 24px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #3b82f6; }
            QTableWidget { background: #15181f; color: #f1f5f9; border: 1px solid #222733; border-radius: 6px; font-size: 11px; gridline-color: #1e222b; }
            QHeaderView::section { background: #1a1d24; color: #94a3b8; padding: 6px 8px; border: none; font-weight: 600; font-size: 11px; }
            QPushButton { background: #1e2430; color: #cbd5e1; border: 1px solid #2e384d; border-radius: 6px; padding: 6px 16px; font-size: 11px; font-weight: 500; }
            QPushButton:hover { background: #2b3548; color: #ffffff; border-color: #3b82f6; }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Title
        hdr_row = QHBoxLayout()
        lbl_title = QLabel("📖 XPath Selector Index & Quality Guide")
        lbl_title.setStyleSheet("color: #60a5fa; font-size: 15px; font-weight: bold;")
        hdr_row.addWidget(lbl_title)
        hdr_row.addStretch()
        main_layout.addLayout(hdr_row)

        # Tab Widget
        tabs = QTabWidget()
        tabs.addTab(self._create_badges_tab(), "🏷️ Badges & Risk Index")
        tabs.addTab(self._create_tiers_tab(), "🎯 Ranking Tiers (T1–T8)")
        tabs.addTab(self._create_stability_tab(), "📊 Stability Scoring")
        main_layout.addWidget(tabs)

        # Footer Button
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); color: #ffffff; border: 1px solid #60a5fa; border-radius: 6px; padding: 7px 24px; font-weight: bold; } QPushButton:hover { background: #1d4ed8; }")
        btn_close.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        main_layout.addLayout(btn_row)

    def _create_badges_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)

        # 1. Localization Risk (Loc Risk)
        loc_card = self._create_info_card(
            title="🌐 Loc Risk (Localization Risk)",
            badge_text="🌐 Loc Risk",
            badge_style="background: #271c19; color: #fb923c; border: 1px solid #7c2d12; padding: 2px 8px; border-radius: 4px; font-weight: bold;",
            description=(
                "<b>What it is:</b> The XPath relies on human-readable text attributes (like <code>@Name='Save'</code> or <code>@HelpText</code>).<br><br>"
                "<b>Why it matters:</b> If your test runs on an operating system or application translated into other languages "
                "(e.g., German <i>'Speichern'</i>, French <i>'Enregistrer'</i>, Spanish <i>'Guardar'</i>), text-based selectors will <b>fail to find the element</b>.<br><br>"
                "<b>Best Practice:</b> Always prefer <code>@AutomationId</code> selectors (Tier 1/2), which have <b>zero localization risk</b> because developer-assigned IDs never change across locales."
            )
        )
        content_layout.addWidget(loc_card)

        # 2. Positional Fragility
        pos_card = self._create_info_card(
            title="⚠️ Positional Fragility",
            badge_text="⚠️ Positional",
            badge_style="background: #3a1515; color: #f87171; border: 1px solid #7f1d1d; padding: 2px 8px; border-radius: 4px; font-weight: bold;",
            description=(
                "<b>What it is:</b> The XPath relies on a hardcoded sibling index (e.g. <code>//Button[3]</code> or <code>(//Window)[2]</code>).<br><br>"
                "<b>Why it matters:</b> If a new button, toolbar item, or menu is added anywhere before this element, "
                "the index shifts and your automation script clicks the wrong element or errors out.<br><br>"
                "<b>Best Practice:</b> Use indexed selectors as a last resort or when disambiguating identical sibling windows."
            )
        )
        content_layout.addWidget(pos_card)

        # 3. Match Verification Badges
        match_card = self._create_info_card(
            title="✅ Verification & Match Statuses",
            badge_text="✅ Unique / ⚠️ Multiple / ❌ Zero",
            badge_style="background: #064e3b; color: #34d399; border: 1px solid #059669; padding: 2px 8px; border-radius: 4px; font-weight: bold;",
            description=(
                "• <span style='color: #34d399; font-weight: bold;'>✅ Unique (1 match):</span> Verified in the live in-memory UI tree. Appium is guaranteed to locate exactly 1 target element.<br>"
                "• <span style='color: #fbbf24; font-weight: bold;'>⚠️ Multiple (N matches):</span> Matches more than 1 element across the tree. Click the badge to expand the <i>Ordered Matches Drawer</i> to inspect each match in tree order or copy unique indexed variants <code>(xpath)[i]</code>.<br>"
                "• <span style='color: #f87171; font-weight: bold;'>❌ 0 matches:</span> The selector syntax failed to match any node in the current tree snapshot."
            )
        )
        content_layout.addWidget(match_card)

        # 4. Top Match Badge
        top_card = self._create_info_card(
            title="★ #1 Top Match",
            badge_text="★ #1 Recommended",
            badge_style="background: #1e3a8a; color: #93c5fd; border: 1px solid #3b82f6; padding: 2px 8px; border-radius: 4px; font-weight: bold;",
            description=(
                "<b>What it is:</b> Automatically ranked as the highest-quality selector for production test automation. "
                "It synthesizes 100% uniqueness, lowest localization dependency, and fastest Appium driver execution."
            )
        )
        content_layout.addWidget(top_card)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)
        return container

    def _create_tiers_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        lbl_desc = QLabel("xGen generates candidates across 8 hierarchical tiers, strictly conforming to the Appium Windows Driver-supported XPath subset:")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        layout.addWidget(lbl_desc)

        table = QTableWidget(9, 4)
        table.setHorizontalHeaderLabels(["Tier", "Strategy Pattern", "Example XPath", "Reliability"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        tiers_data = [
            ("T1", "Global AutomationId", "//*[@AutomationId='btn_save']", "🟢 Highest (100)"),
            ("T2", "Type + AutomationId", "//Button[@AutomationId='btn_save']", "🟢 Highest (95)"),
            ("T3", "Global Name", "//*[@Name='Save Document']", "🟡 Good (80)"),
            ("T3A", "Name Substring", "//*[contains(@Name, 'Save')]", "🟡 Good (75)"),
            ("T4", "Type + Name", "//Button[@Name='Save Document']", "🟡 Good (75)"),
            ("T5", "Parent / Ancestor Scoped", "//Window[@Name='App']//Button[@Name='Save']", "🟡 Moderate (70)"),
            ("T6", "Parent ID + Sibling Index", "//*[@AutomationId='toolbar']//Button[1]", "🟠 Fragile (55)"),
            ("T6A", "Indexed Disambiguation", "(//Window[starts-with(@Name, 'App')]//Button)[2]", "🟠 Moderate (65)"),
            ("T7/T8", "Positional / Diagnostic Path", "/Desktop/Window[1]/Pane[2]/Button[1]", "🔴 Lowest (30)"),
        ]

        for row, (tier, strat, ex, rel) in enumerate(tiers_data):
            it_tier = QTableWidgetItem(tier)
            it_tier.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_strat = QTableWidgetItem(strat)
            it_ex = QTableWidgetItem(ex)
            it_rel = QTableWidgetItem(rel)

            table.setItem(row, 0, it_tier)
            table.setItem(row, 1, it_strat)
            table.setItem(row, 2, it_ex)
            table.setItem(row, 3, it_rel)

        layout.addWidget(table)
        return container

    def _create_stability_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        c_layout = QVBoxLayout(content)
        c_layout.setSpacing(12)

        card_score = self._create_info_card(
            title="📊 Stability Score Formula (0 to 100)",
            badge_text="0 – 100 Scale",
            badge_style="background: #1e2433; color: #60a5fa; border: 1px solid #3b82f6; padding: 2px 8px; border-radius: 4px; font-weight: bold;",
            description=(
                "xGen calculates a quantitative stability score for every generated selector based on 4 key factors:<br><br>"
                "<b>1. Attribute Durability (Base 40–80 pts):</b><br>"
                "• <code>AutomationId</code>: +80 points (developer-defined, non-transient)<br>"
                "• <code>Name</code> / Title: +60 points (reliable but locale-dependent)<br>"
                "• <code>ClassName</code>: +40 points (styling-tied)<br><br>"
                "<b>2. Multi-Window Desktop Penalty (-10 pts):</b><br>"
                "When running in Desktop Root mode, selectors lacking a container or Window anchor receive a penalty.<br><br>"
                "<b>3. Localization Risk Penalty (-15 pts):</b><br>"
                "Deducted if the selector relies solely on human-readable text when localization risk is active.<br><br>"
                "<b>4. Positional Fragility Penalty (-25 pts):</b><br>"
                "Deducted when indices (e.g. <code>[3]</code>) are present due to high vulnerability to layout shifts."
            )
        )
        c_layout.addWidget(card_score)

        card_rating = self._create_info_card(
            title="🎯 Score Rating Bands",
            badge_text="Quality Levels",
            badge_style="background: #14171e; color: #f1f5f9; border: 1px solid #2a3140; padding: 2px 8px; border-radius: 4px;",
            description=(
                "• <span style='color: #34d399; font-weight: bold;'>🟢 Stable (80 – 100):</span> Recommended for production regression CI test suites.<br>"
                "• <span style='color: #fbbf24; font-weight: bold;'>🟡 Moderate (60 – 79):</span> Solid for localized test suites; verify periodically.<br>"
                "• <span style='color: #f87171; font-weight: bold;'>🔴 Fragile (< 60):</span> Use only as a temporary diagnostic selector."
            )
        )
        c_layout.addWidget(card_rating)
        c_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)
        return container

    def _create_info_card(self, title: str, badge_text: str, badge_style: str, description: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet("background: #14171e; border: 1px solid #232834; border-radius: 8px; padding: 4px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        hdr = QHBoxLayout()
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #f1f5f9; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        hdr.addWidget(lbl_t)
        hdr.addStretch()

        lbl_b = QLabel(badge_text)
        lbl_b.setStyleSheet(badge_style)
        hdr.addWidget(lbl_b)
        layout.addLayout(hdr)

        lbl_d = QLabel(description)
        lbl_d.setWordWrap(True)
        lbl_d.setTextFormat(Qt.TextFormat.RichText)
        lbl_d.setStyleSheet("color: #cbd5e1; font-size: 11px; line-height: 1.5; border: none; background: transparent; padding-top: 4px;")
        layout.addWidget(lbl_d)

        return card
