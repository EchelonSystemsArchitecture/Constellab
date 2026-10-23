"""Day 25: simulated Earth-observation targets and geospatial event sources.

Earth-observation targets are **configurable data**, not code: stable IDs,
lat/lon (or a circular region via ``radius_km``), an active time interval in
simulation seconds, urgency, an observation-confidence prior, what an
observation requires in order to count as usable, and a separate ``truth``
payload.

The ground-truth separation is the whole point of the gate: policy inputs see
only :func:`EventTarget.observable_view` — identity, kind, timing, urgency,
requirements — while completion/failure decisions later consult ``truth``
(simulator side, never the learning side).

Event traces are *generated* through a plugin-style ``EventSource`` registry.
Sources are deterministic functions of ``(seed, spec)``; built-in kinds are a
wildfire-like hotspot, a flood-like region change and generic change detection.
Adding a source means registering it, never editing the event loop.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SUPPORTED_EVENT_KINDS: tuple[str, ...] = ("hotspot", "flood-region", "change-detection")

EVENT_SOURCE_VERSION = "event-source-1"


class TargetError(ValueError):
    """A target or event-source spec is invalid; the trace stays untouched."""


def _require_number(name: str, value: Any, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise TargetError(f"{name} must be a finite number, got {value!r}")
    v = float(value)
    if v < minimum or v > maximum:
        raise TargetError(f"{name} must be within [{minimum}, {maximum}], got {v}")
    return v


@dataclass
class EventTarget:
    """One simulated EO target (or event region) with stable identity."""

    id: str
    kind: str
    lat_deg: float
    lon_deg: float
    start_s: float
    end_s: float
    radius_km: float = 10.0
    urgency: int = 3
    confidence: float = 0.5
    requirements: dict[str, float] = field(default_factory=dict)
    truth: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise TargetError("target id must be a non-empty string")
        if self.kind not in SUPPORTED_EVENT_KINDS:
            raise TargetError(
                f"target kind {self.kind!r} must be one of {SUPPORTED_EVENT_KINDS}"
            )
        self.lat_deg = _require_number("lat_deg", self.lat_deg, -90.0, 90.0)
        self.lon_deg = _require_number("lon_deg", self.lon_deg, -180.0, 180.0)
        self.start_s = _require_number("start_s", self.start_s, 0.0, 3.15e10)
        self.end_s = _require_number("end_s", self.end_s, 0.0, 3.15e10)
        if self.end_s <= self.start_s:
            raise TargetError(
                f"target {self.id}: end_s ({self.end_s}) must exceed start_s ({self.start_s})"
            )
        self.radius_km = _require_number("radius_km", self.radius_km, 0.0, 2_000.0)
        if not isinstance(self.urgency, int) or isinstance(self.urgency, bool) or not 1 <= self.urgency <= 5:
            raise TargetError(f"target {self.id}: urgency must be an integer in [1, 5], got {self.urgency!r}")
        self.confidence = _require_number("confidence", self.confidence, 0.0, 1.0)
        if not isinstance(self.requirements, dict):
            raise TargetError(f"target {self.id}: requirements must be a mapping")
        for name in self.requirements:
            _require_number(f"requirements.{name}", self.requirements[name], 0.0, 1e12)
        if not isinstance(self.truth, dict):
            raise TargetError(f"target {self.id}: truth must be a mapping (ground-truth payload)")

    @property
    def active_s(self) -> float:
        return self.end_s - self.start_s

    def is_active(self, time_s: float) -> bool:
        return self.start_s <= time_s < self.end_s

    def observable_view(self, time_s: float | None = None) -> dict[str, Any]:
        """What any consumer (renderer, policy) may see: **no truth payload**."""
        view = {
            "id": self.id,
            "kind": self.kind,
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "radius_km": self.radius_km,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "status": "active" if (time_s is None or self.is_active(time_s)) else "ended",
            "urgency": self.urgency,
            "requirements": dict(self.requirements),
        }
        # The observation-confidence prior is observable; its graded truth is not.
        view["confidence"] = self.confidence
        return view

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "radius_km": self.radius_km,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "requirements": dict(self.requirements),
            "truth": dict(self.truth),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EventTarget":
        return cls(
            id=str(payload.get("id", "")),
            kind=str(payload.get("kind", "")),
            lat_deg=payload.get("lat_deg", 0.0),   # type: ignore[arg-type]
            lon_deg=payload.get("lon_deg", 0.0),   # type: ignore[arg-type]
            start_s=payload.get("start_s", 0.0),   # type: ignore[arg-type]
            end_s=payload.get("end_s", 0.0),       # type: ignore[arg-type]
            radius_km=payload.get("radius_km", 10.0) or 10.0,   # type: ignore[arg-type]
            urgency=payload.get("urgency", 3),     # type: ignore[arg-type]
            confidence=payload.get("confidence", 0.5),   # type: ignore[arg-type]
            requirements=dict(payload.get("requirements") or {}),
            truth=dict(payload.get("truth") or {}),
        )


def validate_trace(targets: Sequence[EventTarget]) -> list[dict[str, str]]:
    """Trace-level checks: stable unique ids and a live-event lifecycle."""
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for target in targets:
        path = f"$targets/{target.id}"
        if target.id in seen:
            issues.append({"path": path, "message": f"duplicate target id {target.id!r}"})
        seen.add(target.id)
        if target.end_s <= target.start_s:
            issues.append({"path": path, "message": "empty or negative time interval"})
    return issues


def active_trace(targets: Sequence[EventTarget], time_s: float) -> list[EventTarget]:
    """Targets observable at ``time_s``, in stable id order."""
    return [t for t in sorted(targets, key=lambda x: x.id) if t.is_active(time_s)]


def observable_events(targets: Sequence[EventTarget], time_s: float) -> list[dict[str, Any]]:
    """The full trace filtered to what is observable at ``time_s``; no truth."""
    return [t.observable_view(time_s) for t in active_trace(targets, time_s)]


# --- event source registry ------------------------------------------------------------

EventSourceFn = Callable[[random.Random, Mapping[str, Any]], list[EventTarget]]

# The event loop stays identical for every source: it receives no generator
# code and can not alter what a source produces — it only consumes traces.


def hotspot_source(rng: random.Random, spec: Mapping[str, Any]) -> list[EventTarget]:
    """Wildfire-like hotspots: point-like, high urgency, short lifetime."""
    count = int(spec.get("count", 4))
    horizon = float(spec.get("horizon_s", 3_600.0))
    spread_deg = float(spec.get("spread_deg", 5.0))
    targets: list[EventTarget] = []
    for index in range(count):
        start = round(rng.uniform(0.05, 0.5) * horizon, 3)
        duration = round(rng.uniform(600.0, 1_800.0), 3)
        truth = {
            "intensity_mw": round(rng.uniform(5.0, 60.0), 3),
            "perimeter_growth_km_h": round(rng.uniform(0.0, 2.0), 3),
        }
        targets.append(
            EventTarget(
                id=f"fire-{index:02d}",
                kind="hotspot",
                lat_deg=round(rng.uniform(-spread_deg, spread_deg), 5),
                lon_deg=round(rng.uniform(-spread_deg, spread_deg), 5),
                start_s=start,
                end_s=min(horizon, start + duration),
                radius_km=round(rng.uniform(0.5, 4.0), 3),
                urgency=rng.choice([4, 5, 5]),
                confidence=round(rng.uniform(0.6, 0.99), 3),
                requirements={"min_confidence": 0.5},
                truth=truth,
            )
        )
    return targets


def flood_source(rng: random.Random, spec: Mapping[str, Any]) -> list[EventTarget]:
    """Flood-like region change: large radius, moderate urgency, long lifetime."""
    count = int(spec.get("count", 2))
    horizon = float(spec.get("horizon_s", 7_200.0))
    flood_count = max(1, count)
    targets: list[EventTarget] = []
    for index in range(flood_count):
        start = round(rng.uniform(0.0, 0.3) * horizon, 3)
        duration = round(rng.uniform(3_600.0, horizon), 3)
        truth = {
            "water_level_change_m": round(rng.uniform(-3.0, 3.0), 3),
            "cloud_cover_fraction": round(rng.uniform(0.0, 0.6), 3),
        }
        targets.append(
            EventTarget(
                id=f"flood-{index:02d}",
                kind="flood-region",
                lat_deg=round(rng.uniform(-20.0, 20.0), 5),
                lon_deg=round(rng.uniform(-20.0, 20.0), 5),
                start_s=start,
                end_s=min(horizon, start + duration),
                radius_km=round(rng.uniform(20.0, 120.0), 3),
                urgency=rng.choice([2, 3, 4]),
                confidence=round(rng.uniform(0.3, 0.9), 3),
                requirements={"min_resolution_m": 30.0},
                truth=truth,
            )
        )
    return targets


def change_detection_source(rng: random.Random, spec: Mapping[str, Any]) -> list[EventTarget]:
    """Generic change detection: mixed urgency, needs a repeat observation."""
    count = int(spec.get("count", 3))
    horizon = float(spec.get("horizon_s", 5_400.0))
    targets: list[EventTarget] = []
    for index in range(max(1, count)):
        start = round(rng.uniform(0.1, 0.6) * horizon, 3)
        duration = round(rng.uniform(900.0, 2_400.0), 3)
        truth = {
            "change_fraction": round(rng.uniform(0.02, 0.4), 4),
            "requires_revisit": True,
        }
        targets.append(
            EventTarget(
                id=f"change-{index:02d}",
                kind="change-detection",
                lat_deg=round(rng.uniform(-60.0, 60.0), 5),
                lon_deg=round(rng.uniform(-180.0, 180.0), 5),
                start_s=start,
                end_s=min(horizon, start + duration),
                radius_km=round(rng.uniform(1.0, 15.0), 3),
                urgency=rng.choice([1, 2, 3]),
                confidence=round(rng.uniform(0.2, 0.8), 3),
                requirements={"min_confidence": 0.4, "min_obs_duration_s": 30.0},
                truth=truth,
            )
        )
    return targets


class EventSourceRegistry:
    """Plugin-style registry of deterministic event sources."""

    def __init__(self, *, default_sources: bool = True) -> None:
        self._sources: dict[str, EventSourceFn] = {}
        self._activated: set[str] = set()
        if default_sources:
            self.register("hotspot", hotspot_source)
            self.register("flood-region", flood_source)
            self.register("change-detection", change_detection_source)

    def register(self, name: str, source: EventSourceFn) -> None:
        if not name or not isinstance(name, str) or not name.replace("-", "_").isidentifier():
            raise TargetError(
                f"event-source name {name!r} must be a dotted-free identifier"
                " (letters, digits, underscores, hyphens)"
            )
        if name in self._sources:
            raise TargetError(f"event source {name!r} is already registered")
        self._sources[name] = source

    def activate(self, name: str) -> None:
        if name not in self._sources:
            raise TargetError(
                f"event source {name!r} is not registered; registered: {sorted(self._sources)}"
            )
        self._activated.add(name)

    def activate_all(self, names: Sequence[str] | None = None) -> None:
        for name in list(names or self._sources):
            self.activate(name)

    def registered(self) -> list[str]:
        return sorted(self._sources)

    def activated(self) -> list[str]:
        return sorted(self._activated)

    def generate_source(self, name: str, seed: int, spec: Mapping[str, Any] | None = None) -> list[EventTarget]:
        """Same name/seed/spec ⇒ same trace segment; sources never share state."""
        if name in self._activated and name not in self._sources:
            raise TargetError(f"activated source {name!r} vanished from the registry")
        if name not in self._sources:
            raise TargetError(f"unknown event source {name!r} (registered: {sorted(self._sources)})")
        rng = random.Random(seed)
        return self._sources[name](rng, spec or {})

    def generate(self, seed: int, config: Mapping[str, Mapping[str, Any]] | None = None) -> list[EventTarget]:
        """A full trace from every **activated** source, in registry order.

        Two activated sources never collide because target ids embed the
        source name; the event loop itself stays untouched.
        """
        names = sorted(self._activated)
        if not names:
            raise TargetError("no event source is activated; nothing generates a trace")
        targets: list[EventTarget] = []
        for name in names:
            spec = dict((config or {}).get(name, {}))  # type: ignore[arg-type]
            source_seed = int(hashlib_seed(f"{EVENT_SOURCE_VERSION}|{name}|{seed}"))
            for target in self.generate_source(name, source_seed, spec):
                targets.append(
                    EventTarget(
                        **{**target.to_dict(), "id": f"{name}.{target.id}"},
                    )
                )
        issues = validate_trace(targets)
        if issues:
            raise TargetError(f"; ".join(i["message"] for i in issues))
        return targets


def hashlib_seed(text: str) -> int:
    """A small, stable 31-bit seed derivation for per-source RNG streams."""
    import hashlib

    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def trace_report(targets: Sequence[EventTarget]) -> dict[str, Any]:
    """Machine-readable summary of a trace set (counts per kind, span, ids)."""
    kinds: dict[str, int] = {}
    for target in targets:
        kinds[target.kind] = kinds.get(target.kind, 0) + 1
    starts = [t.start_s for t in targets]
    ends = [t.end_s for t in targets]
    return {
        "count": len(targets),
        "kinds": kinds,
        "ids": [t.id for t in sorted(targets, key=lambda x: x.id)],
        "span_s": [min(starts), max(ends)] if targets else [0.0, 0.0],
    }


def load_target_file(path: Path) -> list[EventTarget]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = payload.get("targets") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise TargetError("a target file must hold a targets list")
    return [EventTarget.from_dict(entry) for entry in raw]
