"""
JSON Schema definitions for xGen Recorder DTOs and options.
Pure Python mapping conforming to JSON Schema Draft-07.
Zero Qt dependencies.
"""
from __future__ import annotations

from typing import Any, Dict


def get_step_schema() -> Dict[str, Any]:
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Step",
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Unique UUID for the step"},
            "seq": {"type": "integer", "description": "1-based monotonic sequence number"},
            "action": {
                "type": "string",
                "enum": [
                    "click", "double_click", "right_click", "type",
                    "key_press", "scroll", "drag_drop", "switch_window", "wait", "assert"
                ]
            },
            "created_at": {"type": "string", "description": "ISO-8601 wall clock timestamp"},
            "monotonic_ms": {"type": "integer", "description": "Monotonic timestamp in milliseconds"},
            "process": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "exe_name": {"type": "string"},
                    "exe_path": {"type": "string"},
                    "bundle_id": {"type": "string"},
                    "app_name": {"type": "string"}
                },
                "required": ["pid"]
            },
            "window": {
                "type": "object",
                "properties": {
                    "handle": {"type": "integer"},
                    "title": {"type": "string"},
                    "class_name": {"type": "string"}
                },
                "required": ["handle"]
            },
            "params": {"type": "object", "description": "Action payload arguments"},
            "resolution": {
                "type": "string",
                "enum": ["native_exact", "scene_cache", "coordinates_only"]
            },
            "locators": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "xpath": {"type": "string"},
                        "tier": {"type": "string"},
                        "stability_score": {"type": "integer"},
                        "state": {"type": "string"}
                    },
                    "required": ["xpath", "tier"]
                }
            },
            "selected_locator": {"type": ["integer", "null"]},
            "locator_state": {"type": "string"},
            "flags": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"}
        },
        "required": ["id", "seq", "action", "created_at", "monotonic_ms", "process", "window"]
    }


def get_recording_meta_schema() -> Dict[str, Any]:
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "RecordingMeta",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "schema_version": {"type": "integer", "default": 1},
            "tool_version": {"type": "string"},
            "platform": {"type": "string"},
            "dialect_key": {"type": "string"},
            "started_at": {"type": "string"},
            "stopped_at": {"type": ["string", "null"]},
            "step_count": {"type": "integer"},
            "duration_seconds": {"type": "number"}
        },
        "required": ["id", "name", "started_at"]
    }


def get_recording_schema() -> Dict[str, Any]:
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Recording",
        "type": "object",
        "properties": {
            "meta": get_recording_meta_schema(),
            "steps": {
                "type": "array",
                "items": get_step_schema()
            }
        },
        "required": ["meta", "steps"]
    }
