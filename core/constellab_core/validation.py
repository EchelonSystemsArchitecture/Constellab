"""Minimal, dependency-free JSON Schema validator for the contract subset.

Only the keywords used by ``simulation_contract.schema.json`` are implemented.
Any other keyword raises ``UnsupportedSchema`` so a schema change can never be
silently ignored. The TypeScript twin lives in ``frontend/src/contract/validate.ts``;
both must agree and are contract-tested against the same fixtures.
"""

from __future__ import annotations

import re
from typing import Any

SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$ref", "$defs", "title", "description", "default", "x-schema-version",
    "type", "required", "properties", "additionalProperties", "enum", "const",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "items", "x-unique-by",
})


class UnsupportedSchema(Exception):
    """The schema uses a keyword this validator does not implement."""


def _type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"unsupported python value: {type(value).__name__}")


def _matches_type(value: Any, expected: str) -> bool:
    actual = _type_of(value)
    if expected == "number":
        return actual in ("number", "integer")
    if expected == "integer":
        return actual == "integer" or (actual == "number" and float(value).is_integer())
    return actual == expected


class SchemaValidator:
    """Validate instances against ``$defs`` entries of one root schema."""

    def __init__(self, root: dict[str, Any]):
        self.root = root
        self._check_supported(root)

    def _check_supported(self, node: Any) -> None:
        for key, child in node.items():
            if key in ("properties", "$defs"):
                for sub in child.values():
                    self._check_supported(sub)
            elif key == "items":
                self._check_supported(child)
            elif key not in SUPPORTED_KEYWORDS:
                raise UnsupportedSchema(f"unsupported schema keyword: {key}")

    def resolve(self, ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise UnsupportedSchema(f"only local $ref is supported, got {ref}")
        node: Any = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def validate(self, instance: Any, ref: str) -> list[dict[str, str]]:
        """Return a list of ``{"path", "message"}`` errors; empty means valid."""
        errors: list[dict[str, str]] = []
        self._validate(instance, self.resolve(ref), "$", errors)
        return errors

    def _validate(self, value: Any, schema: dict[str, Any], path: str, errors: list[dict[str, str]]) -> None:
        if "$ref" in schema:
            merged = {**self.resolve(schema["$ref"]), **{k: v for k, v in schema.items() if k != "$ref"}}
            self._validate(value, merged, path, errors)
            return

        expected = schema.get("type")
        if expected is not None and not _matches_type(value, expected):
            errors.append({"path": path, "message": f"must be {expected}, got {_type_of(value)}"})
            return

        if "const" in schema and value != schema["const"]:
            errors.append({"path": path, "message": f"must equal {schema['const']!r}"})
        if "enum" in schema and value not in schema["enum"]:
            errors.append({"path": path, "message": f"must be one of {schema['enum']!r}"})

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append({"path": path, "message": f"must be >= {schema['minimum']}"})
            if "maximum" in schema and value > schema["maximum"]:
                errors.append({"path": path, "message": f"must be <= {schema['maximum']}"})
            if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
                errors.append({"path": path, "message": f"must be > {schema['exclusiveMinimum']}"})
            if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
                errors.append({"path": path, "message": f"must be < {schema['exclusiveMaximum']}"})

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append({"path": path, "message": f"must have at least {schema['minLength']} characters"})
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append({"path": path, "message": f"must have at most {schema['maxLength']} characters"})
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                errors.append({"path": path, "message": f"must match pattern {schema['pattern']}"})

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append({"path": path, "message": f"must have at least {schema['minItems']} items"})
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append({"path": path, "message": f"must have at most {schema['maxItems']} items"})
            if "items" in schema:
                for index, item in enumerate(value):
                    self._validate(item, schema["items"], f"{path}[{index}]", errors)
            if "x-unique-by" in schema:
                key = schema["x-unique-by"]
                seen: dict[Any, int] = {}
                for index, item in enumerate(value):
                    if isinstance(item, dict) and key in item:
                        ident = item[key]
                        if ident in seen:
                            errors.append({
                                "path": f"{path}[{index}].{key}",
                                "message": f"duplicate {key} {ident!r} (first seen at {path}[{seen[ident]}])",
                            })
                        else:
                            seen[ident] = index

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for name in schema.get("required", []):
                if name not in value:
                    errors.append({"path": f"{path}.{name}", "message": "missing required field"})
            for name, child in value.items():
                if name in properties:
                    self._validate(child, properties[name], f"{path}.{name}", errors)
                elif schema.get("additionalProperties") is False:
                    errors.append({"path": f"{path}.{name}", "message": "unknown field"})
