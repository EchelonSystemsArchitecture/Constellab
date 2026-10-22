"""Day 19: the dynamic parameter registry.

Thousands of configurable values must not become thousands of branches. Every
runtime variable is a :class:`ParameterSpec`: a namespaced key, the component
that consumes it, a type, a unit, bounds, an enum, a distribution, a
normalization for model encoders, mutability, update cadence, model visibility
and a schema version.

The registry is **data**: ``data/parameters/*.json`` holds one file per owner
component, and the loader is the only code that knows the file format. A
parameter with no registered consumer is never silently accepted: configuration
validation rejects it with the field path, and :meth:`ParameterRegistry.audit`
lists every unconsumed or metadata-only key.

Keys are fully qualified (``power.solar-battery.array_area_m2``) in the registry
and short (``array_area_m2``) inside a component's ``parameters`` object, where
the component type already supplies the owner. Numeric parameter keys end with
the slug of their unit (see ``units.unit_slug``), so a key can not claim one unit
while the registry says another.

``schema_hash`` is the stable identity of the parameter surface: it excludes
display metadata (label, description), so renaming a label never changes model
meaning, while any semantic change (type, unit, bounds, default) does.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .units import UnitError, key_matches_unit, unit_kind, unit_slug

DATA_DIR = Path(__file__).with_name("data") / "parameters"

PARAMETER_SCHEMA_VERSION = 1
PARAMETER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$")
OWNER_PATTERN = PARAMETER_KEY_PATTERN
KINDS = ("number", "integer", "boolean", "string")
DISTRIBUTIONS = ("constant", "uniform", "log-uniform", "normal")
MUTABILITY = ("static", "run")
STATUS_CONSUMED = "consumed"
STATUS_METADATA_ONLY = "metadata_only"

_SPEC_FIELDS = (
    "key", "owner", "kind", "label", "unit", "default", "minimum", "maximum", "enum",
    "distribution", "normalization", "mutability", "update_cadence_s", "model_visible",
    "schema_version", "description",
)


class ParameterError(ValueError):
    """One or more parameter definitions or values are invalid."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("parameter error: " + "; ".join(f"{i['path']}: {i['message']}" for i in issues))


@dataclass(frozen=True)
class ParameterSpec:
    """One configurable runtime variable and the component that consumes it."""

    key: str
    owner: str
    kind: str = "number"
    label: str = ""
    unit: str = "1"
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[Any, ...] = ()
    distribution: str = "constant"
    normalization: dict[str, float] = field(default_factory=dict)
    mutability: str = "static"
    update_cadence_s: float | None = None
    model_visible: bool = True
    schema_version: int = PARAMETER_SCHEMA_VERSION
    description: str = ""

    @property
    def short_key(self) -> str:
        prefix = self.owner + "."
        return self.key[len(prefix):] if self.key.startswith(prefix) else self.key

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "owner": self.owner,
            "kind": self.kind,
            "unit": self.unit,
            "unit_slug": unit_slug(self.unit) if self.kind == "number" else "",
            "default": self.default,
            "distribution": self.distribution,
            "mutability": self.mutability,
            "model_visible": self.model_visible,
            "schema_version": self.schema_version,
        }
        if self.label:
            payload["label"] = self.label
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.enum:
            payload["enum"] = list(self.enum)
        if self.normalization:
            payload["normalization"] = dict(self.normalization)
        if self.update_cadence_s is not None:
            payload["update_cadence_s"] = self.update_cadence_s
        if self.description:
            payload["description"] = self.description
        return payload

    def semantic_dict(self) -> dict[str, Any]:
        """The fields that define model meaning (display metadata excluded)."""
        return {
            "key": self.key,
            "owner": self.owner,
            "kind": self.kind,
            "unit": self.unit,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "enum": list(self.enum),
            "distribution": self.distribution,
            "normalization": {k: self.normalization[k] for k in sorted(self.normalization)},
            "mutability": self.mutability,
            "update_cadence_s": self.update_cadence_s,
            "model_visible": self.model_visible,
            "schema_version": self.schema_version,
        }

    def normalized(self, value: float) -> float:
        """Map a value into a model-friendly range using its declared norm."""
        scale = float(self.normalization.get("scale", 1.0))
        offset = float(self.normalization.get("offset", 0.0))
        if scale == 0.0:
            raise ZeroDivisionError(f"parameter {self.key!r} normalization scale is zero")
        return (float(value) - offset) / scale

    def with_label(self, label: str) -> "ParameterSpec":
        """Display-only change: the schema hash must not move."""
        return replace(self, label=label)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _type_matches(kind: str, value: Any) -> bool:
    if kind == "number":
        return _is_number(value)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    return False


def spec_issues(spec: ParameterSpec, path: str = "$") -> list[dict[str, str]]:
    """Everything wrong with one definition, with a field-path diagnostic each."""

    def issue(suffix: str, message: str) -> None:
        issues.append({"path": f"{path}.{suffix}" if suffix else path, "message": message})

    issues: list[dict[str, str]] = []

    if not isinstance(spec.key, str) or not PARAMETER_KEY_PATTERN.fullmatch(spec.key):
        issue("key", f"parameter key {spec.key!r} must be lower-case, dot-separated namespacing with [a-z0-9_-] segments")
    if not isinstance(spec.owner, str) or not OWNER_PATTERN.fullmatch(spec.owner):
        issue("owner", f"owner {spec.owner!r} must be a registered component key")
    elif isinstance(spec.key, str) and not spec.key.startswith(spec.owner + "."):
        issue("key", f"parameter key {spec.key!r} must be namespaced under its owner {spec.owner!r}")
    if spec.kind not in KINDS:
        issue("kind", f"kind must be one of {', '.join(KINDS)}, got {spec.kind!r}")

    try:
        kind_of_unit = unit_kind(spec.unit)
    except UnitError as exc:
        kind_of_unit = None
        issue("unit", str(exc))
    else:
        if spec.kind in ("number", "integer") and spec.unit == "":
            issue("unit", "numeric parameters need an explicit unit ('1' for a ratio)")
        if spec.kind == "number" and isinstance(spec.key, str) and not key_matches_unit(spec.key, spec.unit):
            issue("unit", f"numeric key {spec.key!r} must end with _{unit_slug(spec.unit)} for unit {spec.unit!r}")

    if spec.default is None and spec.kind != "string":
        issue("default", "a default is required so a scenario can omit the parameter")
    elif spec.default is not None and not _type_matches(spec.kind, spec.default):
        issue("default", f"default {spec.default!r} is not a {spec.kind}")

    for bound, name in ((spec.minimum, "minimum"), (spec.maximum, "maximum")):
        if bound is not None and not _is_number(bound):
            issue(name, f"{name} must be a finite number")
    if _is_number(spec.minimum) and _is_number(spec.maximum) and spec.minimum > spec.maximum:
        issue("minimum", f"minimum {spec.minimum:g} exceeds maximum {spec.maximum:g}")
    if _is_number(spec.default):
        if _is_number(spec.minimum) and spec.default < spec.minimum:
            issue("default", f"default {spec.default:g} is below minimum {spec.minimum:g}")
        if _is_number(spec.maximum) and spec.default > spec.maximum:
            issue("default", f"default {spec.default:g} is above maximum {spec.maximum:g}")
    if spec.enum:
        if spec.default is not None and spec.default not in spec.enum:
            issue("default", f"default {spec.default!r} is not one of {list(spec.enum)!r}")
        for value in spec.enum:
            if not _type_matches(spec.kind, value):
                issue("enum", f"enum value {value!r} is not a {spec.kind}")

    if spec.distribution not in DISTRIBUTIONS:
        issue("distribution", f"distribution must be one of {', '.join(DISTRIBUTIONS)}")
    if spec.distribution == "log-uniform" and _is_number(spec.minimum) and spec.minimum <= 0:
        issue("distribution", "log-uniform sampling needs a positive minimum")

    if spec.normalization:
        unknown = set(spec.normalization) - {"scale", "offset"}
        if unknown:
            issue("normalization", f"unknown normalization keys: {', '.join(sorted(unknown))}")
        scale = spec.normalization.get("scale", 1.0)
        offset = spec.normalization.get("offset", 0.0)
        if not _is_number(scale) or float(scale) == 0.0:
            issue("normalization", "scale must be a finite non-zero number")
        if not _is_number(offset):
            issue("normalization", "offset must be a finite number")

    if spec.mutability not in MUTABILITY:
        issue("mutability", f"mutability must be one of {', '.join(MUTABILITY)}")
    if spec.update_cadence_s is not None and (not _is_number(spec.update_cadence_s) or spec.update_cadence_s <= 0):
        issue("update_cadence_s", "update cadence must be a positive number of simulated seconds")
    if not isinstance(spec.schema_version, int) or isinstance(spec.schema_version, bool) or spec.schema_version < 1:
        issue("schema_version", "schema_version must be a positive integer")
    if not isinstance(spec.model_visible, bool):
        issue("model_visible", "model_visible must be a boolean")
    return issues


@dataclass(frozen=True)
class ParameterMigration:
    """A declared rename between parameter schema versions."""

    from_version: int
    to_version: int
    renames: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"from_version": self.from_version, "to_version": self.to_version,
                "renames": dict(self.renames)}


class ParameterRegistry:
    """Validated parameter definitions, keyed by fully qualified name."""

    def __init__(self, specs: Iterable[ParameterSpec] = (), *, source: str = "<memory>"):
        self.source = source
        self._specs: dict[str, ParameterSpec] = {}
        self._migrations: list[ParameterMigration] = []
        issues: list[dict[str, str]] = []
        for spec in specs:
            issues.extend(self._register(spec))
        if issues:
            raise ParameterError(issues)

    # -- registration ---------------------------------------------------------

    def _register(self, spec: ParameterSpec) -> list[dict[str, str]]:
        issues = spec_issues(spec, f"{self.source}:{spec.key}")
        if issues:
            return issues
        if spec.key in self._specs:
            return [{"path": f"{self.source}:{spec.key}",
                     "message": f"duplicate parameter definition for {spec.key!r}"}]
        self._specs[spec.key] = spec
        return []

    def register(self, spec: ParameterSpec) -> ParameterSpec:
        issues = self._register(spec)
        if issues:
            raise ParameterError(issues)
        return spec

    def extend(self, specs: Iterable[ParameterSpec]) -> None:
        batch = list(specs)
        added: list[str] = []
        issues: list[dict[str, str]] = []
        for spec in batch:
            before = set(self._specs)
            issues.extend(self._register(spec))
            added.extend(set(self._specs) - before)
        if issues:
            # Leave the registry untouched when any part of the batch is bad.
            for key in added:
                self._specs.pop(key, None)
            raise ParameterError(issues)

    def add_migration(self, migration: ParameterMigration) -> None:
        if migration.to_version <= migration.from_version:
            raise ParameterError([{"path": "migration.to_version",
                                   "message": "to_version must be greater than from_version"}])
        for source_key, target_key in migration.renames.items():
            if target_key not in self._specs:
                raise ParameterError([{"path": f"migration.renames.{source_key}",
                                       "message": f"target parameter {target_key!r} is not registered"}])
            if source_key in self._specs:
                raise ParameterError([{"path": f"migration.renames.{source_key}",
                                       "message": f"source parameter {source_key!r} is still registered"}])
        self._migrations.append(migration)

    # -- lookup ---------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, key: str) -> bool:
        return key in self._specs

    def get(self, key: str) -> ParameterSpec:
        try:
            return self._specs[key]
        except KeyError:
            raise ParameterError([{"path": key, "message": f"unregistered parameter {key!r}"}]) from None

    def specs(self) -> list[ParameterSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def owners(self) -> list[str]:
        return sorted({spec.owner for spec in self._specs.values()})

    def by_owner(self, owner: str) -> list[ParameterSpec]:
        return [self._specs[key] for key in sorted(self._specs) if self._specs[key].owner == owner]

    def defaults_for(self, owner: str) -> dict[str, Any]:
        """Short-key defaults for one owner component."""
        return {spec.short_key: spec.default for spec in self.by_owner(owner)}

    def canonical_key(self, owner: str, short_key: str) -> str:
        return short_key if short_key.startswith(owner + ".") else f"{owner}.{short_key}"

    # -- identity -------------------------------------------------------------

    def schema_hash(self) -> str:
        """SHA-256 of the semantic parameter surface, stable under label edits."""
        canonical = json.dumps(
            [self._specs[key].semantic_dict() for key in sorted(self._specs)],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": PARAMETER_SCHEMA_VERSION,
            "schema_hash": self.schema_hash(),
            "count": len(self._specs),
            "owners": self.owners(),
            "migrations": [migration.to_dict() for migration in self._migrations],
            "parameters": [spec.to_dict() for spec in self.specs()],
        }

    # -- validation -----------------------------------------------------------

    def validate_values(self, owner: str, values: Mapping[str, Any], *,
                        path: str = "$.parameters") -> list[dict[str, str]]:
        """Check a component's short-key parameter map against its definitions."""
        issues: list[dict[str, str]] = []
        if not isinstance(values, Mapping):
            return [{"path": path, "message": f"expected an object of parameters, got {type(values).__name__}"}]
        known = {spec.short_key: spec for spec in self.by_owner(owner)}
        for key in values:
            if key not in known:
                issue = self._owner_of_short_key(key)
                message = (f"parameter {key!r} is consumed by {issue!r}, not by {owner!r}; "
                           f"move it to that component") if issue else (
                    f"parameter {key!r} has no registered consumer: it would not change behaviour")
                issues.append({"path": f"{path}.{key}", "message": message})
        for short_key, spec in sorted(known.items()):
            if short_key not in values:
                continue
            value = values[short_key]
            field_path = f"{path}.{short_key}"
            if not _type_matches(spec.kind, value):
                issues.append({"path": field_path,
                               "message": f"must be {spec.kind} in {spec.unit!r}, got {value!r}"})
                continue
            if _is_number(value):
                if spec.minimum is not None and value < spec.minimum:
                    issues.append({"path": field_path,
                                   "message": f"must be >= {spec.minimum:g} {spec.unit}"})
                if spec.maximum is not None and value > spec.maximum:
                    issues.append({"path": field_path,
                                   "message": f"must be <= {spec.maximum:g} {spec.unit}"})
            if spec.enum and value not in spec.enum:
                issues.append({"path": field_path, "message": f"must be one of {list(spec.enum)!r}"})
        return issues

    def _owner_of_short_key(self, short_key: str) -> str | None:
        matches = [spec.owner for spec in self._specs.values() if spec.short_key == short_key]
        return matches[0] if matches else None

    def effective_values(self, owner: str, values: Mapping[str, Any] | None = None, *,
                         path: str = "$.parameters") -> dict[str, Any]:
        """Defaults merged with supplied values; raises on any invalid value."""
        supplied = dict(values or {})
        issues = self.validate_values(owner, supplied, path=path)
        if issues:
            raise ParameterError(issues)
        merged = self.defaults_for(owner)
        merged.update(supplied)
        return merged

    def audit(self, configured: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
        """Classify configured keys: consumed, metadata-only, or unconsumed.

        ``configured`` maps an owner component key to its short-key value map.
        Metadata-only keys are legitimate settings that must not be fed to a
        model encoder (``model_visible`` false), and are reported separately so
        nobody mistakes them for inputs.
        """
        consumed: list[str] = []
        metadata_only: list[str] = []
        unconsumed: list[str] = []
        for owner, values in configured.items():
            known = {spec.short_key: spec for spec in self.by_owner(owner)}
            for key in values:
                full = self.canonical_key(owner, key)
                spec = known.get(key)
                if spec is None:
                    unconsumed.append(full)
                elif spec.model_visible:
                    consumed.append(full)
                else:
                    metadata_only.append(full)
        return {"consumed": sorted(consumed), "metadata_only": sorted(metadata_only),
                "unconsumed": sorted(unconsumed)}

    def migrate(self, values: Mapping[str, Any], *, from_version: int) -> tuple[int, dict[str, Any]]:
        """Apply declared renames until no migration starts at the current version."""
        current = from_version
        migrated = dict(values)
        applied: set[int] = set()
        while True:
            candidates = [m for m in self._migrations if m.from_version == current]
            if not candidates:
                return current, migrated
            if current in applied:
                raise ParameterError([{"path": "migration",
                                       "message": f"migration cycle at schema version {current}"}])
            applied.add(current)
            migration = candidates[0]
            for source_key, target_key in migration.renames.items():
                if source_key in migrated:
                    migrated[target_key] = migrated.pop(source_key)
            current = migration.to_version


# --- data loading ----------------------------------------------------------------


def _spec_from_payload(payload: Mapping[str, Any], owner: str, source: str) -> ParameterSpec:
    unknown = set(payload) - set(_SPEC_FIELDS) - {"key", "owner"}
    if not unknown and "owner" in payload:
        unknown = {"owner"}
    if unknown:
        raise ParameterError([{"path": f"{source}:{payload.get('key', '?')}",
                               "message": f"unknown spec fields: {', '.join(sorted(unknown))}"}])
    fields = {name: payload[name] for name in _SPEC_FIELDS if name in payload}
    short = fields.pop("key", None)
    if not isinstance(short, str) or not short:
        raise ParameterError([{"path": source, "message": "every parameter needs a key"}])
    fields["key"] = f"{owner}.{short}"
    fields["owner"] = owner
    if "enum" in fields:
        fields["enum"] = tuple(fields["enum"])
    if not isinstance(fields.get("enum", ()), tuple):
        raise ParameterError([{"path": f"{source}:{short}", "message": "enum must be a list"}])
    try:
        return ParameterSpec(**fields)
    except TypeError as exc:
        raise ParameterError([{"path": f"{source}:{short}", "message": str(exc)}]) from None


def load_registry(directory: Path | None = None) -> ParameterRegistry:
    """Load every ``*.json`` owner file from ``directory`` (default: package data)."""
    root = directory or DATA_DIR
    specs: list[ParameterSpec] = []
    sources: dict[str, str] = {}
    if not root.exists():
        return ParameterRegistry()
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ParameterError([{"path": path.name, "message": f"unreadable parameter file: {exc}"}]) from None
        owner = payload.get("owner")
        if not isinstance(owner, str) or not OWNER_PATTERN.fullmatch(owner):
            raise ParameterError([{"path": path.name,
                                   "message": f"file must declare a namespaced 'owner', got {owner!r}"}])
        if owner in sources:
            raise ParameterError([{"path": path.name,
                                   "message": f"owner {owner!r} is already defined by {sources[owner]}"}])
        sources[owner] = path.name
        entries = payload.get("parameters")
        if not isinstance(entries, list):
            raise ParameterError([{"path": path.name, "message": "'parameters' must be a list"}])
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ParameterError([{"path": path.name, "message": "each parameter must be an object"}])
            specs.append(_spec_from_payload(entry, owner, path.name))
    return ParameterRegistry(specs, source=str(root))


_BUILTIN: ParameterRegistry | None = None


def builtin_registry() -> ParameterRegistry:
    """Process-wide registry loaded from the shipped data files."""
    global _BUILTIN
    if _BUILTIN is None:
        _BUILTIN = load_registry()
    return _BUILTIN


def stress_registry(count: int) -> ParameterRegistry:
    """Deterministic synthetic registry for load/validation stress tests.

    ``count`` definitions spread over owners of four parameters each. The keys,
    bounds and distributions vary so hashing and validation touch real branches
    instead of one repeated shape.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    owners = max(1, math.ceil(count / 4))
    specs: list[ParameterSpec] = []
    for owner_index in range(owners):
        owner = f"stress.owner-{owner_index:04d}"
        for slot in range(4):
            if len(specs) >= count:
                break
            unit = ("m", "W", "J", "s")[slot]
            kind = "number"
            specs.append(ParameterSpec(
                key=f"{owner}.field_{slot:02d}_{unit_slug(unit)}",
                owner=owner,
                kind=kind,
                label=f"Stress field {slot}",
                unit=unit,
                default=float(slot + 1),
                # log-uniform slot: a positive minimum is part of its own
                # validation, so the synthetic registry must honour it too.
                minimum=1.0 if slot == 3 else 0.0,
                maximum=float(1000 * (slot + 1)),
                distribution=("constant", "uniform", "normal", "log-uniform")[slot],
                normalization={"scale": float(slot + 1), "offset": 0.0},
                mutability=("static", "run", "static", "run")[slot],
                update_cadence_s=float(10 * (slot + 1)),
                model_visible=slot != 3,
                description="Synthetic parameter used to stress the registry; no component consumes it.",
            ))
    return ParameterRegistry(specs, source="<stress>")


def registry_payload(registry: ParameterRegistry | None = None) -> dict[str, Any]:
    return (registry or builtin_registry()).payload()
