"""
Raw JSON Recording Exporter.
Lossless serialization of entire Recording document.
Zero Qt dependencies.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from xgen.recorder.models import ExportResult, Recording
from xgen.recorder.ports.exporter import Exporter


class RawJsonExporter(Exporter):
    """
    Exports full Recording model as formatted JSON.
    """
    id = "raw_json"
    display_name = "Raw Recording JSON"
    file_extension = "json"

    def option_schema(self) -> Mapping[str, Any]:
        return {
            "indent": {"type": "integer", "default": 2}
        }

    def export(self, recording: Recording, options: Mapping[str, Any]) -> ExportResult:
        indent = int(options.get("indent", 2))
        data = recording.to_dict()
        text = json.dumps(data, indent=indent, ensure_ascii=False)

        base_name = recording.meta.name.strip().replace(" ", "_") if recording.meta.name else recording.meta.id
        filename = f"{base_name}_raw.json"

        return ExportResult(
            text=text,
            filename=filename,
            stats={"step_count": len(recording.steps)}
        )