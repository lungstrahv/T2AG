#!/usr/bin/env python3
"""Fail-closed validator for the bridge contract's JSON Schema subset."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """The document or schema violates the frozen V1 contract."""


ALLOWED_KEYWORDS = {
    "$schema",
    "$id",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "const",
    "enum",
    "pattern",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "items",
    "format",
}
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
SEMANTIC_EXCLUDES = {
    "semantic_sha256",
    "generated_at",
    "event_id",
    "export_id",
    "contribution_id",
}


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON number is forbidden: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_strict(raw: bytes | str | Path) -> Any:
    if isinstance(raw, Path):
        data = raw.read_bytes()
    elif isinstance(raw, str):
        data = raw.encode("utf-8")
    else:
        data = raw
    if b"\x00" in data:
        raise ContractError("NUL is forbidden")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("JSON must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    def reject_non_finite(node: Any) -> None:
        if isinstance(node, float) and not math.isfinite(node):
            raise ContractError("non-finite JSON number is forbidden")
        if isinstance(node, dict):
            for key, child in node.items():
                if not isinstance(key, str) or "\x00" in key:
                    raise ContractError("JSON object keys must be NUL-free strings")
                reject_non_finite(child)
        elif isinstance(node, list):
            for child in node:
                reject_non_finite(child)
        elif isinstance(node, str) and "\x00" in node:
            raise ContractError("NUL is forbidden")

    reject_non_finite(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def semantic_projection(document: dict[str, Any]) -> dict[str, Any]:
    schema = document.get("schema")
    excludes = set(SEMANTIC_EXCLUDES)
    if schema == "reading.t2ag_receipt.v1":
        excludes -= {"contribution_id"}
    return {key: value for key, value in document.items() if key not in excludes}


def semantic_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(semantic_projection(document))).hexdigest()


def _schema_keywords(schema: Any, where: str = "$") -> None:
    if not isinstance(schema, dict):
        raise ContractError(f"schema node must be an object: {where}")
    unknown = sorted(set(schema) - ALLOWED_KEYWORDS)
    if unknown:
        raise ContractError(f"unsupported schema keyword at {where}: {unknown}")
    properties = schema.get("properties", {})
    if properties and not isinstance(properties, dict):
        raise ContractError(f"properties must be an object: {where}")
    for key, child in properties.items():
        _schema_keywords(child, f"{where}.properties.{key}")
    if "items" in schema:
        _schema_keywords(schema["items"], f"{where}.items")


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_format(value: str, format_name: str, where: str) -> None:
    if format_name == "date-time":
        if not value.endswith("Z"):
            raise ContractError(f"date-time must use UTC Z: {where}")
        try:
            parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ContractError(f"invalid date-time: {where}") from exc
        if parsed.tzinfo != dt.timezone.utc:
            raise ContractError(f"date-time must use UTC: {where}")
        return
    if format_name == "posix-relative-path":
        if (
            not value
            or value.startswith(("/", "\\"))
            or "\\" in value
            or "%" in value
            or ":" in value
            or value.startswith("file://")
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ContractError(f"invalid POSIX relative path: {where}")
        return
    raise ContractError(f"unsupported schema format: {format_name}")


def _validate(value: Any, schema: dict[str, Any], where: str) -> None:
    expected = schema.get("type")
    if expected is not None:
        choices = expected if isinstance(expected, list) else [expected]
        if not choices or not all(isinstance(item, str) for item in choices):
            raise ContractError(f"invalid schema type declaration: {where}")
        if not any(_type_matches(value, item) for item in choices):
            raise ContractError(f"wrong type at {where}: expected {choices}")
    if "const" in schema and value != schema["const"]:
        raise ContractError(f"const mismatch at {where}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"enum mismatch at {where}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ContractError(f"invalid required declaration: {where}")
        missing = sorted(set(required) - set(value))
        if missing:
            raise ContractError(f"missing fields at {where}: {missing}")
        if schema.get("additionalProperties") is not False:
            raise ContractError(f"object schema must fail closed: {where}")
        extra = sorted(set(value) - set(properties))
        if extra:
            raise ContractError(f"unknown fields at {where}: {extra}")
        for key, child in value.items():
            _validate(child, properties[key], f"{where}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ContractError(f"too few items at {where}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractError(f"too many items at {where}")
        item_schema = schema.get("items")
        if item_schema is None:
            raise ContractError(f"array schema lacks items: {where}")
        for index, child in enumerate(value):
            _validate(child, item_schema, f"{where}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ContractError(f"string too short at {where}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ContractError(f"string too long at {where}")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            raise ContractError(f"pattern mismatch at {where}")
        if "format" in schema:
            _validate_format(value, schema["format"], where)


def validate_document(document: Any, schema: dict[str, Any]) -> None:
    if schema.get("$schema") != SCHEMA_URI:
        raise ContractError("schema must declare Draft 2020-12")
    _schema_keywords(schema)
    _validate(document, schema, "$")
