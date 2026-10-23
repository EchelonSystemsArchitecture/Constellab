"""Day 29: geometry-driven inter-satellite contact opportunities.

A contact opportunity is a **predicted, physical** thing: two satellites are
within a link's range and the straight line between them clears the Earth. It
does not mean a message was sent — delivery is Day 30's transport problem — and
nothing here is drawn by the renderer; the plan comes from orbital state and the
declared link configuration.

Link capability lives behind a :class:`LinkModel` plugin registry. A fleet can
fly a wide-beam UHF radio (long range, low bandwidth) or a narrow optical
terminal (short range, high bandwidth); topology changes when the declared
configuration changes, which is the acceptance criterion for this day.

Three reference arrangements are shipped as scenario payloads:

* ``fully-connected`` — a tight cluster whose members all see each other,
* ``intermittently-connected`` — crossing planes where links open and close,
* ``disconnected`` — two clusters beyond each other's range,

Each carries the same explicit fidelity assumptions: spherical Earth for limb
occlusion, straight-line (vacuum) propagation, no atmospheric or antenna
modelling, and no scheduling or pointing dynamics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from .frames import EARTH_EQUATORIAL_RADIUS_KM

Vector3 = tuple[float, float, float]

CONTACT_VERSION = "contact-opportunities-1"

FIDELITY = (
    "range is a straight-line Euclidean distance between instantaneous ECI positions",
    "Earth limb occlusion uses a spherical Earth (equatorial radius); no atmosphere, terrain or terrain mask",
    "a link exists while both range and limb clearance pass; pointing, antenna gain and scheduling are not modelled",
    "contact opportunities are predictions from orbit state, not evidence that a message was delivered",
)

LinkConfigValue = float | int | str


class ContactError(ValueError):
    """A link model, its configuration or a contact query is invalid."""


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v: Vector3) -> float:
    return math.sqrt(_dot(v, v))


def _finite(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ContactError(f"{name} must be a finite number, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class LinkConfig:
    """Effective, validated parameters for one link model."""

    model: str
    max_range_km: float = 4_000.0
    bandwidth_bps: float = 1.0e8
    latency_s: float = 0.01
    min_clearance_km: float = 100.0
    quality_floor: float = 0.1

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model:
            raise ContactError("link model key must be a non-empty string")
        for name in ("max_range_km", "bandwidth_bps", "latency_s", "min_clearance_km"):
            _finite(name, getattr(self, name))
        if self.max_range_km <= 0.0:
            raise ContactError("max_range_km must be positive")
        if self.bandwidth_bps <= 0.0:
            raise ContactError("bandwidth_bps must be positive")
        if self.latency_s < 0.0:
            raise ContactError("latency_s must be non-negative")
        if not 0.0 <= self.quality_floor <= 1.0:
            raise ContactError("quality_floor must be within [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_range_km": self.max_range_km,
            "bandwidth_bps": self.bandwidth_bps,
            "latency_s": self.latency_s,
            "min_clearance_km": self.min_clearance_km,
            "quality_floor": self.quality_floor,
        }


@runtime_checkable
class LinkModel(Protocol):
    """A communication capability selected by key, not branched on in the loop."""

    key: str
    label: str
    fidelity: tuple[str, ...]
    defaults: Mapping[str, LinkConfigValue]

    def config(self, values: Mapping[str, Any] | None = None) -> LinkConfig:
        """Merge the model defaults with scenario overrides."""


class _BaseLink:
    key = "link.base"
    label = "Link"
    fidelity = FIDELITY
    defaults: dict[str, LinkConfigValue] = {}

    def config(self, values: Mapping[str, Any] | None = None) -> LinkConfig:
        merged: dict[str, Any] = dict(self.defaults)
        known = set(LinkConfig.__dataclass_fields__) - {"model"}
        unknown = sorted(set(values or {}) - known - {"model"})
        if unknown:
            raise ContactError(
                f"link model {self.key!r} has no parameter(s) {', '.join(unknown)}; "
                f"known: {', '.join(sorted(known))}"
            )
        merged.update(values or {})
        merged["model"] = self.key
        filtered = {k: v for k, v in merged.items() if k in known or k == "model"}
        for name in ("max_range_km", "bandwidth_bps", "latency_s", "min_clearance_km", "quality_floor"):
            if name in filtered:
                filtered[name] = _finite(name, filtered[name])
        return LinkConfig(**filtered)


class UhfLink(_BaseLink):
    """Wide-beam radio: thousands of kilometres, modest bandwidth, real latency."""

    key = "link.uhf"
    label = "UHF wide-beam radio"
    defaults = {
        "max_range_km": 6_000.0,
        "bandwidth_bps": 9_600.0,
        "latency_s": 0.12,
        "min_clearance_km": 50.0,
        "quality_floor": 0.2,
    }


class OpticalLink(_BaseLink):
    """Narrow optical terminal: short range, high bandwidth, small latency."""

    key = "link.optical"
    label = "Optical cross-link"
    defaults = {
        "max_range_km": 4_000.0,
        "bandwidth_bps": 1.0e8,
        "latency_s": 0.005,
        "min_clearance_km": 150.0,
        "quality_floor": 0.1,
    }


_REGISTRY: dict[str, LinkModel] = {}


def register_link_model(model: LinkModel) -> LinkModel:
    key = getattr(model, "key", None)
    if not isinstance(key, str) or not key:
        raise ContactError("a link model must declare a non-empty string key")
    if key in _REGISTRY:
        raise ContactError(f"link model {key!r} is already registered")
    _REGISTRY[key] = model
    return model


def unregister_link_model(key: str) -> LinkModel | None:
    return _REGISTRY.pop(key, None)


def link_model(key: str) -> LinkModel:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ContactError(
            f"unknown link model {key!r}; registered models: {', '.join(sorted(_REGISTRY)) or '(none)'}"
        ) from None


def registered_link_models() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def link_models_payload() -> dict[str, Any]:
    return {
        "version": CONTACT_VERSION,
        "fidelity": list(FIDELITY),
        "models": [
            {"key": key, "label": model.label, "defaults": dict(model.defaults)}
            for key, model in sorted(_REGISTRY.items())
        ],
    }


for _model in (UhfLink(), OpticalLink()):
    register_link_model(_model)


# --- pair geometry ------------------------------------------------------------------

@dataclass(frozen=True)
class LinkGeometry:
    """Instantaneous geometry of one satellite pair."""

    time_s: float
    range_km: float
    clearance_km: float
    in_range: bool
    clear: bool
    quality: float

    @property
    def visible(self) -> bool:
        return self.in_range and self.clear

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": self.time_s,
            "range_km": round(self.range_km, 6),
            "clearance_km": round(self.clearance_km, 6),
            "in_range": self.in_range,
            "clear": self.clear,
            "quality": round(self.quality, 6),
            "visible": self.visible,
        }


def _limb_clearance_km(a: Vector3, b: Vector3) -> float:
    """Minimum distance from Earth's centre to the a→b segment, minus the radius."""
    ab = _sub(b, a)
    denom = _dot(ab, ab)
    if denom <= 0.0:
        return _norm(a) - EARTH_EQUATORIAL_RADIUS_KM
    t = max(0.0, min(1.0, -_dot(a, ab) / denom))
    closest = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return _norm(closest) - EARTH_EQUATORIAL_RADIUS_KM


def link_geometry(a_km: Vector3, b_km: Vector3, config: LinkConfig, *, time_s: float = 0.0) -> LinkGeometry:
    """Range, limb clearance and a quality proxy for one pair at one instant."""
    distance = _norm(_sub(b_km, a_km))
    clearance = _limb_clearance_km(a_km, b_km)
    in_range = distance <= config.max_range_km
    clear = clearance >= config.min_clearance_km
    if in_range and clear:
        range_margin = 1.0 - distance / config.max_range_km
        clearance_margin = min(1.0, clearance / max(config.min_clearance_km, 1e-9) / 4.0)
        quality = max(config.quality_floor, 0.7 * range_margin + 0.3 * clearance_margin)
    else:
        quality = 0.0
    return LinkGeometry(
        time_s=float(time_s),
        range_km=distance,
        clearance_km=clearance,
        in_range=in_range,
        clear=clear,
        quality=max(0.0, min(1.0, quality)),
    )


# --- contact plan -------------------------------------------------------------------

@dataclass
class ContactOpportunity:
    """One contiguous interval in which a pair can exchange messages."""

    a_id: str
    b_id: str
    model: str
    start_s: float
    end_s: float
    min_range_km: float
    max_range_km: float
    mean_quality: float
    sample_count: int = 0

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def pair(self) -> tuple[str, str]:
        return (self.a_id, self.b_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "a": self.a_id,
            "b": self.b_id,
            "model": self.model,
            "start_s": round(self.start_s, 6),
            "end_s": round(self.end_s, 6),
            "duration_s": round(self.duration_s, 6),
            "min_range_km": round(self.min_range_km, 6),
            "max_range_km": round(self.max_range_km, 6),
            "mean_quality": round(self.mean_quality, 6),
            "sample_count": self.sample_count,
        }


PositionFn = Callable[[float], Vector3]


def contact_plan(
    positions: Mapping[str, PositionFn],
    *,
    config: LinkConfig,
    horizon_s: float,
    step_s: float = 30.0,
) -> list[ContactOpportunity]:
    """Deterministic contact opportunities for every pair of satellites.

    Pairs are formed in sorted id order, so the plan and its order never depend
    on dictionary insertion order.
    """
    if step_s <= 0.0:
        raise ContactError("step_s must be positive")
    if horizon_s < 0.0:
        raise ContactError("horizon_s must be non-negative")
    ids = sorted(positions)
    opportunities: list[ContactOpportunity] = []
    for index, a_id in enumerate(ids):
        for b_id in ids[index + 1:]:
            samples: list[LinkGeometry] = []
            ranges: list[float] = []
            qualities: list[float] = []
            index_s = 0
            steps = int(math.floor(horizon_s / step_s)) + 1
            while index_s < steps:
                time_s = round(index_s * step_s, 9)
                geometry = link_geometry(
                    positions[a_id](time_s), positions[b_id](time_s), config, time_s=time_s
                )
                if geometry.visible:
                    samples.append(geometry)
                    ranges.append(geometry.range_km)
                    qualities.append(geometry.quality)
                elif samples:
                    opportunities.append(ContactOpportunity(
                        a_id=a_id, b_id=b_id, model=config.model,
                        start_s=samples[0].time_s, end_s=samples[-1].time_s,
                        min_range_km=min(ranges), max_range_km=max(ranges),
                        mean_quality=sum(qualities) / len(qualities),
                        sample_count=len(samples),
                    ))
                    samples, ranges, qualities = [], [], []
                index_s += 1
            if samples:
                opportunities.append(ContactOpportunity(
                    a_id=a_id, b_id=b_id, model=config.model,
                    start_s=samples[0].time_s, end_s=samples[-1].time_s,
                    min_range_km=min(ranges), max_range_km=max(ranges),
                    mean_quality=sum(qualities) / len(qualities),
                    sample_count=len(samples),
                ))
    opportunities.sort(key=lambda item: (item.start_s, item.a_id, item.b_id))
    return opportunities


def positions_from_config(config: Any) -> dict[str, PositionFn]:
    """Position functions for every satellite, propagated by the scenario's model."""
    from .dynamics import DEFAULT_MODEL_KEY, dynamics_model

    model = dynamics_model(getattr(config, "dynamics_model", None) or DEFAULT_MODEL_KEY)
    return {
        satellite.id: (lambda time_s, orbit=satellite.orbit: model.state_at(orbit, time_s)[0])
        for satellite in config.satellites
    }


def contact_plan_for_config(
    config: Any,
    *,
    link_key: str = "link.optical",
    link_values: Mapping[str, Any] | None = None,
    horizon_s: float,
    step_s: float = 30.0,
) -> list[ContactOpportunity]:
    """Contact plan for a validated scenario using a named link model."""
    link = link_model(link_key).config(link_values)
    return contact_plan(
        positions_from_config(config), config=link, horizon_s=horizon_s, step_s=step_s
    )


# --- topology -----------------------------------------------------------------------

def links_at(plan: Sequence[ContactOpportunity], time_s: float) -> list[tuple[str, str]]:
    """Pairs with an open contact at ``time_s``, in stable order."""
    edges = {
        opportunity.pair
        for opportunity in plan
        if opportunity.start_s <= time_s <= opportunity.end_s
    }
    return sorted(edges)


def connected_components(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    """Connected components of an undirected link graph, stable order."""
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    seen: set[str] = set()
    components: list[list[str]] = []
    for node in sorted(adjacency):
        if node in seen:
            continue
        stack = [node]
        component: list[str] = []
        seen.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in sorted(adjacency[current], reverse=True):
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        components.append(sorted(component))
    return components


def is_connected(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> bool:
    node_list = list(nodes)
    if len(node_list) <= 1:
        return True
    return len(connected_components(node_list, edges)) == 1


def topology_at(plan: Sequence[ContactOpportunity], nodes: Iterable[str], time_s: float) -> dict[str, Any]:
    node_list = sorted(nodes)
    edges = links_at(plan, time_s)
    components = connected_components(node_list, edges)
    return {
        "time_s": round(time_s, 6),
        "links": [{"a": a, "b": b} for a, b in edges],
        "link_count": len(edges),
        "components": components,
        "connected": len(components) <= 1,
    }


def contact_report(plan: Sequence[ContactOpportunity], *, nodes: Iterable[str], horizon_s: float,
                   step_s: float = 30.0) -> dict[str, Any]:
    """Plan summary: per-pair totals and the link count over time."""
    node_list = sorted(nodes)
    pairs: dict[str, dict[str, Any]] = {}
    for opportunity in plan:
        key = f"{opportunity.a_id}|{opportunity.b_id}"
        entry = pairs.setdefault(key, {
            "a": opportunity.a_id,
            "b": opportunity.b_id,
            "windows": 0,
            "contact_s": 0.0,
        })
        entry["windows"] += 1
        entry["contact_s"] += opportunity.duration_s
    timeline = []
    index = 0
    steps = int(math.floor(horizon_s / step_s)) + 1
    while index < steps:
        time_s = round(index * step_s, 6)
        topology = topology_at(plan, node_list, time_s)
        timeline.append({"time_s": time_s, "link_count": topology["link_count"],
                         "connected": topology["connected"]})
        index += 1
    counts = {entry["link_count"] for entry in timeline}
    return {
        "version": CONTACT_VERSION,
        "fidelity": list(FIDELITY),
        "nodes": node_list,
        "pairs": [pairs[key] for key in sorted(pairs)],
        "link_counts": sorted(counts),
        "always_connected": all(entry["connected"] for entry in timeline),
        "ever_connected": any(entry["connected"] for entry in timeline),
        "timeline": timeline,
    }


# --- reference arrangements ----------------------------------------------------------

SCENARIO_EPOCH = "2026-10-12T00:00:00Z"


def _satellite(sat_id: str, *, semi_major_axis_km: float, inclination_deg: float,
               raan_deg: float, true_anomaly_deg: float) -> dict[str, Any]:
    return {
        "id": sat_id,
        "name": sat_id.upper(),
        "orbit": {
            "semi_major_axis_km": semi_major_axis_km,
            "eccentricity": 0.0,
            "inclination_deg": inclination_deg,
            "raan_deg": raan_deg,
            "argument_of_perigee_deg": 0.0,
            "true_anomaly_deg": true_anomaly_deg,
        },
    }


def topology_scenario(kind: str) -> dict[str, Any]:
    """Reference arrangements: validated config payload plus its link override.

    The link choice is returned beside the configuration rather than inside it:
    the Day 2 contract rejects unknown scenario fields, and a communication
    capability is a Day 29 plugin selection, not a contract field.
    """
    if kind == "fully-connected":
        satellites = [
            _satellite(f"sat-{name}", semi_major_axis_km=6928.137, inclination_deg=53.0,
                       raan_deg=0.0, true_anomaly_deg=anomaly)
            for name, anomaly in zip(("alpha", "bravo", "charlie", "delta"), (0.0, 4.0, 8.0, 12.0))
        ]
        scenario_id = "contacts-fully-connected"
        link = {"model": "link.optical", "max_range_km": 4_000.0}
    elif kind == "intermittently-connected":
        # Two crossing planes sharing an ascending-node crossing: the pair is in
        # range near the crossing and far apart a quarter-orbit later, so the
        # link opens and closes twice per revolution.
        satellites = [
            _satellite("sat-alpha", semi_major_axis_km=6928.137, inclination_deg=53.0,
                       raan_deg=0.0, true_anomaly_deg=0.0),
            _satellite("sat-bravo", semi_major_axis_km=6928.137, inclination_deg=97.6,
                       raan_deg=10.0, true_anomaly_deg=0.0),
        ]
        scenario_id = "contacts-intermittent"
        link = {"model": "link.optical", "max_range_km": 4_000.0}
    elif kind == "disconnected":
        satellites = [
            _satellite("sat-alpha", semi_major_axis_km=6928.137, inclination_deg=53.0,
                       raan_deg=0.0, true_anomaly_deg=0.0),
            _satellite("sat-bravo", semi_major_axis_km=6928.137, inclination_deg=53.0,
                       raan_deg=0.0, true_anomaly_deg=5.0),
            _satellite("sat-charlie", semi_major_axis_km=6928.137, inclination_deg=53.0,
                       raan_deg=0.0, true_anomaly_deg=180.0),
            _satellite("sat-delta", semi_major_axis_km=6928.137, inclination_deg=53.0,
                       raan_deg=0.0, true_anomaly_deg=185.0),
        ]
        scenario_id = "contacts-disconnected"
        link = {"model": "link.optical", "max_range_km": 4_000.0}
    else:
        raise ContactError(
            f"unknown topology {kind!r}; expected fully-connected, intermittently-connected or disconnected"
        )
    return {
        "kind": kind,
        "config": {
            "schema_version": "1.0.0",
            "scenario_id": scenario_id,
            "name": f"Contact topology: {kind}",
            "seed": 11,
            "epoch_utc": SCENARIO_EPOCH,
            "satellites": satellites,
        },
        "link": link,
        "fidelity": list(FIDELITY),
    }
