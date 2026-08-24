"""
XML UI Tree Parser and in-memory hierarchical UINode representation.
Normalizes attributes across Appium Windows Driver and legacy WinAppDriver.
"""

from __future__ import annotations

import datetime
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from lxml import etree

from xgen.utils.rect import Rect

logger = logging.getLogger("xgen.parser")


class TreeParseError(Exception):
    """Raised when XML parsing fails or input is malformed."""
    pass


@dataclass(eq=False)
class UINode:
    """In-memory representation of a UI Automation element node."""
    tag: str                                 # e.g. "Button", "Edit", "Window", "Pane"
    attributes: Dict[str, str]               # Normalized PascalCase attribute key-value pairs
    children: List[UINode] = field(default_factory=list)
    parent: Optional[UINode] = None
    depth: int = 0                           # 0 = root
    child_index: int = 1                     # 1-based index among siblings sharing the same tag
    sibling_index: int = 1                   # 1-based index among ALL siblings under same parent
    bounding_rect: Optional[Rect] = None
    runtime_id: str = ""                     # e.g. "42.12345.0"
    is_transient: bool = False
    captured_at: Optional[datetime.datetime] = None
    bridge_confidence: float = 1.0           # 0.0 - 1.0 confidence score from ElementBridge

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UINode):
            return False
        return self is other

    def __hash__(self) -> int:
        return id(self)

    @property
    def automation_id(self) -> str:
        return self.attributes.get("AutomationId", "")

    @property
    def name(self) -> str:
        return self.attributes.get("Name", "")

    @property
    def class_name(self) -> str:
        return self.attributes.get("ClassName", "")

    @property
    def is_enabled(self) -> bool:
        return self.attributes.get("IsEnabled", "true").lower() == "true"

    @property
    def is_offscreen(self) -> bool:
        return self.attributes.get("IsOffscreen", "false").lower() == "true"

    @property
    def help_text(self) -> str:
        return self.attributes.get("HelpText", "")

    @property
    def aria_properties(self) -> str:
        return self.attributes.get("AriaProperties", "")

    @property
    def child_count(self) -> int:
        return len(self.children)

    def is_within_repeating_container(self) -> bool:
        """Check if this element or any of its ancestors sits inside a list/table/datagrid."""
        REPEATING_TAGS = {"List", "ListView", "DataGrid", "Table", "ListBox", "Tree", "TreeView", "ItemsControl"}
        curr = self.parent
        while curr:
            if curr.tag in REPEATING_TAGS:
                return True
            curr = curr.parent
        return False

    def display_label(self) -> str:
        """Returns concise human-readable text for tree widgets."""
        name_str = (self.name[:25] + "…") if len(self.name) > 25 else self.name
        if self.automation_id and self.name:
            return f"{self.tag} \"{name_str}\" [{self.automation_id}]"
        elif self.automation_id:
            return f"{self.tag} [{self.automation_id}]"
        elif self.name:
            return f"{self.tag} \"{name_str}\""
        elif self.class_name:
            return f"{self.tag} ({self.class_name})"
        return self.tag


class TreeParser:
    """Parses raw driver XML into navigable UINode trees."""

    ATTR_ALIASES: Dict[str, str] = {
        "automationid": "AutomationId",
        "automation-id": "AutomationId",
        "classname": "ClassName",
        "class-name": "ClassName",
        "controltype": "ControlType",
        "boundingrectangle": "BoundingRectangle",
        "bounding-rectangle": "BoundingRectangle",
        "isenabled": "IsEnabled",
        "is-enabled": "IsEnabled",
        "isoffscreen": "IsOffscreen",
        "is-offscreen": "IsOffscreen",
        "runtimeid": "RuntimeId",
        "runtime-id": "RuntimeId",
        "name": "Name",
        "helptext": "HelpText",
        "help-text": "HelpText",
        "ariaproperties": "AriaProperties",
        "aria-properties": "AriaProperties",
    }

    ROOT_TAGS = {"AppiumAUT", "Page", "XCUIElementTypeApplication", "Root"}

    @classmethod
    def parse(cls, raw_xml: str) -> UINode:
        """
        Parse raw XML into a root UINode with precalculated depths, indices, and bounds.
        """
        if not raw_xml or not raw_xml.strip():
            raise TreeParseError("Cannot parse empty XML string.")

        try:
            # Parse with lxml
            parser = etree.XMLParser(recover=True, no_network=True)
            root_elem = etree.fromstring(raw_xml.encode("utf-8"), parser=parser)
            if root_elem is None:
                raise TreeParseError("XML parser returned null element.")

            return cls._build_node_recursive(root_elem, parent=None, depth=0)
        except Exception as e:
            if isinstance(e, TreeParseError):
                raise
            raise TreeParseError(f"Failed to parse XML: {e}") from e

    @classmethod
    def _build_node_recursive(cls, elem: etree._Element, parent: Optional[UINode], depth: int) -> UINode:
        # Strip namespace if present: e.g. "{http://...}Button" -> "Button"
        raw_tag = elem.tag
        tag = raw_tag.split("}")[-1] if "}" in raw_tag else raw_tag

        # Normalize attribute keys
        attrs: Dict[str, str] = {}
        for k, v in elem.attrib.items():
            norm_k = cls.ATTR_ALIASES.get(k.lower(), k)
            attrs[norm_k] = str(v)

        bounding_rect = Rect.from_appium_string(attrs.get("BoundingRectangle", ""))
        runtime_id = attrs.get("RuntimeId", "")

        node = UINode(
            tag=tag,
            attributes=attrs,
            children=[],
            parent=parent,
            depth=depth,
            bounding_rect=bounding_rect,
            runtime_id=runtime_id
        )

        # Build children with correct sibling indices
        tag_counts: Dict[str, int] = {}
        child_nodes: List[UINode] = []

        for idx, child_elem in enumerate(elem, start=1):
            if not isinstance(child_elem.tag, str):
                continue  # skip comments or processing instructions

            child_tag = child_elem.tag.split("}")[-1] if "}" in child_elem.tag else child_elem.tag
            tag_counts[child_tag] = tag_counts.get(child_tag, 0) + 1

            child_node = cls._build_node_recursive(child_elem, parent=node, depth=depth + 1)
            child_node.sibling_index = idx
            child_node.child_index = tag_counts[child_tag]
            child_nodes.append(child_node)

        node.children = child_nodes
        return node

    @classmethod
    def to_xml_element(cls, node: UINode, node_map: Optional[Dict[str, UINode]] = None) -> etree._Element:
        """Convert UINode tree back into an lxml Element with internal node UID linking."""
        elem = etree.Element(node.tag)
        for k, v in node.attributes.items():
            elem.set(k, v)
        uid = str(id(node))
        elem.set("_xgen_uid", uid)
        if node_map is not None:
            node_map[uid] = node
        for child in node.children:
            elem.append(cls.to_xml_element(child, node_map))
        return elem

    @classmethod
    def to_xml_string(cls, node: UINode) -> str:
        """Serialize UINode tree to formatted XML string."""
        elem = cls.to_xml_element(node)
        return etree.tostring(elem, encoding="unicode", pretty_print=True)

    @classmethod
    def merge_subtree(cls, root: UINode, subtree: UINode, parent_runtime_id: str = "") -> UINode:
        """
        Graft subtree under the node matching parent_runtime_id (or root if not found).
        """
        target_parent = None
        if parent_runtime_id:
            target_parent = cls.find_by_runtime_id(root, parent_runtime_id)

        if target_parent is None:
            target_parent = root

        # Set parent link and update depth
        subtree.parent = target_parent
        cls._recalculate_depths(subtree, target_parent.depth + 1)

        # Assign sibling indices
        target_parent.children.append(subtree)
        subtree.sibling_index = len(target_parent.children)
        same_tag_count = sum(1 for c in target_parent.children if c.tag == subtree.tag)
        subtree.child_index = same_tag_count

        return root

    @classmethod
    def find_by_runtime_id(cls, root: UINode, runtime_id: str) -> Optional[UINode]:
        """BFS search for a node with the exact RuntimeId."""
        if not runtime_id:
            return None

        queue = deque([root])
        while queue:
            node = queue.popleft()
            if node.runtime_id == runtime_id:
                return node
            queue.extend(node.children)
        return None

    @classmethod
    def find_by_bounding_rect(cls, root: UINode, rect: Rect, tag: str = "") -> List[UINode]:
        """Find all nodes matching bounding rectangle and optional ControlType tag."""
        matches: List[UINode] = []
        queue = deque([root])

        while queue:
            node = queue.popleft()
            if node.bounding_rect and node.bounding_rect.to_tuple() == rect.to_tuple():
                if not tag or node.tag == tag:
                    matches.append(node)
            queue.extend(node.children)

        return matches

    INTERACTIVE_TAGS = {
        "Button", "MenuItem", "TabItem", "CheckBox", "RadioButton",
        "Hyperlink", "ComboBox", "Edit", "ListItem", "TreeItem",
        "HeaderItem", "Slider", "ScrollBar", "Spinner", "ProgressBar"
    }

    @classmethod
    def find_deepest_at_point(cls, root: UINode, x: int, y: int, tag: str = "") -> Optional[UINode]:
        """
        Point-containment hit test: finds all nodes containing screen point (x, y)
        and returns the primary interactive control (e.g. Button, Tab, MenuItem)
        or innermost leaf node.
        """
        candidates: List[UINode] = []
        queue = deque([root])

        while queue:
            node = queue.popleft()
            if node.bounding_rect and node.bounding_rect.contains_point(x, y):
                # Skip full-screen desktop panes
                if not (node.depth <= 1 and node.bounding_rect.width >= 1900 and node.bounding_rect.height >= 1000):
                    if not tag or node.tag == tag:
                        candidates.append(node)
            queue.extend(node.children)

        if not candidates:
            return None

        # Prioritize interactive controls (Button, Tab, MenuItem) over inner text/glyph children or outer panes
        def score_candidate(n: UINode):
            is_interactive = 0 if n.tag in cls.INTERACTIVE_TAGS else 1
            area = n.bounding_rect.area if n.bounding_rect else 99999999
            return (is_interactive, area, -n.depth)

        candidates.sort(key=score_candidate)
        return candidates[0]

    @classmethod
    def get_ancestors(cls, node: UINode) -> List[UINode]:
        """
        Return ancestor chain from node's immediate parent up to (exclusive of) root.
        """
        ancestors: List[UINode] = []
        curr = node.parent
        while curr is not None and curr.parent is not None:
            ancestors.append(curr)
            curr = curr.parent
        return ancestors

    @classmethod
    def node_count(cls, root: UINode) -> int:
        """Count total nodes in tree via BFS."""
        count = 0
        queue = deque([root])
        while queue:
            node = queue.popleft()
            count += 1
            queue.extend(node.children)
        return count

    @classmethod
    def expire_transient_nodes(cls, root: UINode, ttl_minutes: int) -> int:
        """
        Remove is_transient nodes older than ttl_minutes.
        Returns total count of pruned nodes.
        """
        now = datetime.datetime.now()
        threshold = now - datetime.timedelta(minutes=ttl_minutes)
        removed_count = 0

        queue = deque([root])
        while queue:
            node = queue.popleft()
            filtered_children: List[UINode] = []
            for child in node.children:
                if child.is_transient and child.captured_at and child.captured_at < threshold:
                    removed_count += cls.node_count(child)
                else:
                    filtered_children.append(child)
                    queue.append(child)
            node.children = filtered_children

        return removed_count

    @classmethod
    def _recalculate_depths(cls, node: UINode, current_depth: int) -> None:
        node.depth = current_depth
        for child in node.children:
            cls._recalculate_depths(child, current_depth + 1)
