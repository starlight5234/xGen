from __future__ import annotations

from typing import Any, Mapping, Protocol
from xgen.recorder.models import ExportResult, Recording


class Exporter(Protocol):
    """
    Format converter converting a Recording into external artifacts.
    e.g. action_xpath_json, pytest_appium, raw_json.
    """
    id: str
    display_name: str
    file_extension: str

    def option_schema(self) -> Mapping[str, Any]:
        """Returns JSON schema describing options accepted by export()."""
        ...

    def export(self, recording: Recording, options: Mapping[str, Any]) -> ExportResult:
        """Transforms recording into output text or structured script."""
        ...
