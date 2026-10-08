"""
Action-XPath JSON Exporter.
Primary automation tool output mapping 1-based sequence keys to positional action arrays:
  {
    "1": ["click", "//Button[@Name='Submit']"],
    "2": ["type", "//Edit[@AutomationId='txtUsername']", "admin@test.com"],
    "3": ["key_press", "//Edit[@AutomationId='txtUsername']", "ENTER"],
    "4": ["double_click", "//ListItem[@Name='Row 1']"]
  }
Zero Qt dependencies.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping

from xgen.recorder.models import ExportResult, LocatorState, Recording, Step
from xgen.recorder.ports.exporter import Exporter

logger = logging.getLogger("xgen.recorder.exporters.action_xpath_json")


class ActionXpathJsonExporter(Exporter):
    """
    Serializes a recording into a clean, decoupled Action-XPath JSON mapping.
    Positional array structure: [action, xpath, *args].
    """
    id = "action_xpath_json"
    display_name = "Action-XPath JSON"
    file_extension = "json"

    def option_schema(self) -> Mapping[str, Any]:
        return {
            "indent": {"type": "integer", "default": 2},
            "include_unverified": {"type": "boolean", "default": True},
        }

    def export(self, recording: Recording, options: Mapping[str, Any]) -> ExportResult:
        indent = int(options.get("indent", 2))
        include_unverified = bool(options.get("include_unverified", True))

        actions_map: Dict[str, List[Any]] = {}
        warnings: List[str] = []

        # Sort steps by sequence number
        sorted_steps = sorted(recording.steps, key=lambda s: s.seq)

        for i, step in enumerate(sorted_steps):
            key = str(step.seq if step.seq > 0 else (i + 1))
            action_arr = step.to_action_array()

            xpath = action_arr[1] if len(action_arr) > 1 else ""

            # Check locator verification status
            if step.locators:
                idx = step.selected_locator if (step.selected_locator is not None and 0 <= step.selected_locator < len(step.locators)) else 0
                loc = step.locators[idx]
                is_unique = loc.state in (LocatorState.UNIQUE_IN_EVIDENCE, LocatorState.APPIUM_VERIFIED)

                if not is_unique and not include_unverified:
                    action_arr[1] = ""
                    warnings.append(
                        f"Step {key} ({step.action.value}): Suppressed unverified locator '{loc.xpath}' (state: {loc.state.value})"
                    )

            if not action_arr[1]:
                warnings.append(f"Step {key} ({step.action.value}): Unresolved element locator")

            actions_map[key] = action_arr

        text = json.dumps(actions_map, indent=indent, ensure_ascii=False)
        base_name = recording.meta.name.strip().replace(" ", "_") if recording.meta.name else recording.meta.id
        filename = f"{base_name}.json"

        stats = {
            "step_count": len(recording.steps),
            "action_count": len(actions_map),
            "warnings_count": len(warnings),
        }

        return ExportResult(
            text=text,
            filename=filename,
            warnings=warnings,
            stats=stats
        )