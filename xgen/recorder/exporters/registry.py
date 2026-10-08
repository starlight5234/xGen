"""
Exporter Registry.
Provides extensible catalog of recording format converters and exporters.
Zero Qt dependencies.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from xgen.recorder.ports.exporter import Exporter
from xgen.recorder.exporters.action_xpath_json import ActionXpathJsonExporter
from xgen.recorder.exporters.raw_json import RawJsonExporter
from xgen.recorder.exporters.pytest_appium import PytestAppiumExporter

logger = logging.getLogger("xgen.recorder.exporters.registry")


class ExporterRegistry:
    """
    Registry for managing available recording exporters.
    """
    def __init__(self):
        self._exporters: Dict[str, Exporter] = {}

    def register(self, exporter: Exporter) -> None:
        self._exporters[exporter.id] = exporter

    def get(self, exporter_id: str) -> Optional[Exporter]:
        return self._exporters.get(exporter_id)

    def list(self) -> List[Exporter]:
        return list(self._exporters.values())

    def as_dict(self) -> Dict[str, Exporter]:
        return dict(self._exporters)


_GLOBAL_REGISTRY: Optional[ExporterRegistry] = None


def default_registry() -> ExporterRegistry:
    """Returns the default populated ExporterRegistry with built-in exporters."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        reg = ExporterRegistry()
        reg.register(ActionXpathJsonExporter())
        reg.register(RawJsonExporter())
        reg.register(PytestAppiumExporter())
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY


def register_exporter(exporter: Exporter) -> None:
    default_registry().register(exporter)


def get_exporter(exporter_id: str) -> Optional[Exporter]:
    return default_registry().get(exporter_id)


def list_exporters() -> List[Exporter]:
    return default_registry().list()
