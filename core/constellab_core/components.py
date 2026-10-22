"""Day 18: generic virtual spacecraft components and their runtime state.

The simulation loop never branches on a satellite type or a parameter name.
Every behaviour a satellite can have is a registered *component*: a model with a
stable key, a kind (power, storage, compute, sensor, payload, task,
event-source), an update stage (the order pipeline steps run in) and two hooks —
build the initial state, and advance it one ``dt_s``. A satellite exposes
whatever capability mix a scenario declares through config alone; two
interchangeable implementations registered for one kind
(``power.solar-battery`` vs ``power.constant``) prove the interface.

State keys use the key convention documented in ``units.py``: a numeric value
ends with the slug of its unit (``battery_charge_j``, ``stored_bit``), so a
snapshot consumer never has to guess what a number means. Component parameters
come from the Day 19 parameter registry (``data/parameters/*.json``); config
values use short keys here because the component itself supplies the owner.

Cross-component wiring is explicit pipeline data, not branching: each step
receives a :class:`ComponentContext` that earlier stages filled (task active,
data produced this step, aggregate power draw). The runner owns the ordering
and the aggregation, so a component never reaches into another one's state.
Everything here is virtual; no real hardware interface is involved or needed.

The built-in reference components are registered by the Day 20 plugin layer
(``plugins.py``), never in this module, so adding a component means adding a
plugin registration rather than a core-loop edit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .frames import (
    EARTH_EQUATORIAL_RADIUS_KM,
    sun_direction_eci,
    sunlit_fraction,
)
from .parameters import ParameterError, builtin_registry
from .units import unit_slug  # noqa: F401  (kept for the key-convention contract)

Vector3 = tuple[float, float, float]

# Component kinds — the subsystem roles the orchestrating loop understands.
KINDS = (
    "event-source",
    "task",
    "sensor",
    "payload",
    "storage",
    "compute",
    "power",
)

# Update stages: the pipeline runs a satellite's components sorted by (stage,
# key). Smaller stages run first so later stages can read what they published.
# Order: event sources fire, tasks grant activity, sensors measure, payloads
# produce, storage absorbs, compute budgets, power closes the energy budget.
STAGES: dict[str, int] = {
    "event-source": 10,
    "task": 20,
    "sensor": 30,
    "payload": 40,
    "storage": 50,
    "compute": 60,
    "power": 90,
}

SOLAR_FLUX_W_M2 = 1361.0  # ~1 AU total solar irradiance; illustrative constant

COMPONENT_KEY_PATTERN = r"^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$"


class ComponentError(ValueError):
    """A component registration, configuration or runtime update is invalid."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("component error: " + "; ".join(f"{i['path']}: {i['message']}" for i in issues))


@dataclass
class ComponentContext:
    """Pipeline data one satellite's component step trades between components.

    ``power_draw_w`` and ``data_produced_bit`` are aggregates the runner resets
    each step; components add to them. ``task_active`` is decided by a task
    component and read by payloads. ``position_km`` and ``sunlit_ratio`` are
    supplied by the runner from orbital state before any component runs.
    """

    epoch_utc: str
    time_s: float
    dt_s: float
    position_km: Vector3
    sunlit_ratio: float = 1.0
    task_active: bool = False
    power_draw_w: float = 0.0
    data_produced_bit: float = 0.0


@runtime_checkable
class ComponentModel(Protocol):
    """A registered subsystem implementation the loop can select by key."""

    key: str
    label: str
    kind: str
    stage: int
    assumptions: Sequence[str]

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """State dict at the scenario epoch."""

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        """Advance ``state`` in place over ``context.dt_s``."""


# --- registry --------------------------------------------------------------------

_REGISTRY: dict[str, ComponentModel] = {}


def register_component(model: ComponentModel) -> ComponentModel:
    """Register a component under its key; duplicates fail with a diagnostic."""
    import re

    key = getattr(model, "key", None)
    if not isinstance(key, str) or not re.match(COMPONENT_KEY_PATTERN, key):
        raise ComponentError([{
            "path": "component.key",
            "message": f"component key {key!r} must be namespaced like 'power.solar-battery'",
        }])
    kind = getattr(model, "kind", None)
    if kind not in KINDS:
        raise ComponentError([{
            "path": f"component.{key}.kind",
            "message": f"kind must be one of {', '.join(KINDS)}, got {kind!r}",
        }])
    if key in _REGISTRY:
        raise ComponentError([{
            "path": f"component.{key}",
            "message": f"component {key!r} is already registered ({type(_REGISTRY[key]).__name__})",
        }])
    _REGISTRY[key] = model
    return model


def unregister_component(key: str) -> ComponentModel | None:
    """Remove a component (used by teardown and tests)."""
    return _REGISTRY.pop(key, None)


def registered_components() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def component(key: str) -> ComponentModel:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ComponentError([{
            "path": f"component.{key}",
            "message": f"unregistered component {key!r}; registered components: "
                       f"{', '.join(registered_components()) or '(none)'}",
        }]) from None


def describe_components() -> list[dict[str, Any]]:
    """Machine-readable registry description, in stable key order."""
    index = builtin_registry()
    out = []
    for key in sorted(_REGISTRY):
        model = _REGISTRY[key]
        out.append({
            "key": key,
            "label": model.label,
            "kind": model.kind,
            "stage": model.stage,
            "assumptions": list(model.assumptions),
            "parameters": [spec.to_dict() for spec in index.by_owner(key)],
        })
    return out


# --- parameters -------------------------------------------------------------------

def effective_params(key: str, values: Mapping[str, Any] | None, *,
                     path: str = "$") -> dict[str, Any]:
    """Registry defaults merged with configured values; raises on invalid values."""
    try:
        return builtin_registry().effective_values(key, values, path=path)
    except ParameterError as exc:
        raise ComponentError(exc.issues) from None


# --- reference component models ----------------------------------------------------

def _norm(v: Vector3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


class SolarBattery:
    """Photovoltaic array feeding a battery: charge in sunlight, drain in eclipse.

    Assumptions: incidence factor equals the sunlit fraction (the default
    configuration is a sun-tracking array), cylindrical-umbra shadowing,
    first-order charging efficiency, and a load that is the base bus draw plus
    every draw the other components published this step. When the battery is
    empty the loads are still served — a brownout policy is out of scope at
    this fidelity level; the state exposes the charge so one can be applied.
    """

    key = "power.solar-battery"
    label = "Solar array + battery"
    kind = "power"
    stage = STAGES["power"]
    assumptions = (
        "incidence factor = sunlit fraction (sun-tracking array by default); "
        "a nadir-facing array multiplies by the sun/nadir alignment",
        "cylindrical-umbra eclipse, no penumbra",
        "solar flux constant at 1361 W/m^2; no distance, season or degradation model",
        "no brownout scheduling; an empty battery keeps serving loads",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        capacity = float(params["battery_capacity_j"])
        initial_charge = capacity * float(params["initial_charge_ratio"])
        return {
            "battery_charge_j": initial_charge,
            "battery_capacity_j": capacity,
            "state_of_charge_fraction": float(params["initial_charge_ratio"]),
            "generated_w": 0.0,
            "load_w": float(params["base_load_w"]),
            "sunlit_fraction": 1.0,
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        sun = sun_direction_eci(context.epoch_utc, context.time_s)
        if params.get("sun_tracking", True):
            incidence = context.sunlit_ratio
        else:
            # A nadir-facing array has its cell normal pointing back at Earth.
            unit = tuple(-c / _norm(context.position_km) for c in context.position_km)
            incidence = context.sunlit_ratio * max(0.0, unit[0] * sun[0] + unit[1] * sun[1] + unit[2] * sun[2])
        generated = (SOLAR_FLUX_W_M2 * float(params["array_area_m2"])
                     * float(params["efficiency_ratio"]) * incidence)
        self._integrate(state, params, context, generated)

    @staticmethod
    def _integrate(state: dict[str, Any], params: Mapping[str, Any],
                   context: ComponentContext, generated: float) -> None:
        load = float(params["base_load_w"]) + context.power_draw_w
        net = generated - load
        charge = state["battery_charge_j"]
        if net >= 0.0:
            charge = min(state["battery_capacity_j"],
                         charge + net * float(params["charge_efficiency_ratio"]) * context.dt_s)
        else:
            charge = max(0.0, charge + net * context.dt_s)
        state["battery_charge_j"] = charge
        state["state_of_charge_fraction"] = charge / state["battery_capacity_j"]
        state["generated_w"] = generated
        state["load_w"] = load


class ConstantSupply:
    """Regulated supply independent of eclipse (radioisotope/fuel-cell stand-in)."""

    key = "power.constant"
    label = "Constant regulated supply"
    kind = "power"
    stage = STAGES["power"]
    assumptions = (
        "supply is uninterrupted and independent of orbit or eclipse",
        "same first-order battery model as the solar variant",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        capacity = float(params["battery_capacity_j"])
        initial_charge = capacity * float(params["initial_charge_ratio"])
        return {
            "battery_charge_j": initial_charge,
            "battery_capacity_j": capacity,
            "state_of_charge_fraction": float(params["initial_charge_ratio"]),
            "generated_w": float(params["supply_w"]),
            "load_w": float(params["base_load_w"]),
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        SolarBattery._integrate(state, params, context, float(params["supply_w"]))


class RoundRobinTasks:
    """Cycles through ``task_count`` declared tasks, one per task duration.

    A task component publishes whether the satellite's workload is currently
    active; the payload model reads that signal instead of guessing. This is a
    task *scheduler* stand-in: target selection arrives with the Day 25 event
    sources.
    """

    key = "task.round-robin"
    label = "Round-robin task scheduler"
    kind = "task"
    stage = STAGES["task"]
    assumptions = (
        "one task active at a time, equal durations, no interruption",
        "activity signal is always 'active'; target selection comes in a later day",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "current_task_index": int(params["start_index"]),
            "seconds_in_task_s": 0.0,
            "task_duration_s": float(params["task_duration_s"]),
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        duration = state["task_duration_s"]
        state["seconds_in_task_s"] += context.dt_s
        if duration > 0 and state["seconds_in_task_s"] >= duration:
            state["seconds_in_task_s"] -= duration
            state["current_task_index"] = (state["current_task_index"] + 1) % int(params["task_count"])
        context.task_active = True


class ConicalSensor:
    """Conical field of regard whose ground footprint follows altitude.

    The footprint radius is the smaller of the cone's projection onto a
    spherical-Earth approximation (altitude * tan(half-angle)) and the geometric
    horizon radius from the current orbital radius, so a very wide half-angle
    degrades to the horizon instead of claiming half the planet.
    """

    key = "sensor.conical"
    label = "Conical field-of-regard sensor"
    kind = "sensor"
    stage = STAGES["sensor"]
    assumptions = (
        "spherical Earth with the equatorial radius as surface reference",
        "footprint from geometry only; no instrument resolution or pointing model",
        "power draw is proportional to the duty cycle",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "footprint_radius_km": 0.0,
            "half_angle_deg": float(params["half_angle_deg"]),
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        radius = _norm(context.position_km)
        altitude = max(0.0, radius - EARTH_EQUATORIAL_RADIUS_KM)
        cone_radius = altitude * math.tan(math.radians(float(params["half_angle_deg"])))
        horizon_sq = max(0.0, radius * radius - EARTH_EQUATORIAL_RADIUS_KM ** 2)
        state["footprint_radius_km"] = min(cone_radius, math.sqrt(horizon_sq))
        context.power_draw_w += float(params["draw_w"]) * float(params["duty_cycle_ratio"])


class ImagingPayload:
    """Produces data while the task scheduler marks the workload active."""

    key = "payload.imaging"
    label = "Imaging payload"
    kind = "payload"
    stage = STAGES["payload"]
    assumptions = (
        "data rate is constant while active; no collection geometry yet",
        "produced data is handed to the pipeline; storage decides what fits",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "produced_bit": 0.0,
            "last_production_bit": 0.0,
            "seconds_active_s": 0.0,
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        if context.task_active:
            produced = float(params["data_rate_bit_s"]) * context.dt_s
            state["produced_bit"] = state["produced_bit"] + produced
            state["last_production_bit"] = produced
            state["seconds_active_s"] += context.dt_s
            context.power_draw_w += float(params["draw_w"])
            # Hand production to the pipeline: later stages (storage at stage
            # 50) read this aggregate exactly once per step.
            context.data_produced_bit += produced
        else:
            state["last_production_bit"] = 0.0


class BufferStorage:
    """Onboard data buffer: absorbs produced data up to capacity, drains downstream.

    Production is written at ``write_rate_bit_s``; data beyond the write rate
    within one step is counted as dropped (a small-step approximation), as is
    anything that does not fit in the buffer before the drain. Downlink is an
    always-available ground link draining continuously at ``read_rate_bit_s``.
    """

    key = "storage.buffer"
    label = "Onboard data buffer"
    kind = "storage"
    stage = STAGES["storage"]
    assumptions = (
        "capacity is a hard limit; overflow is dropped, not compressed",
        "downlink runs continuously at the configured read rate",
        "production beyond one step's write-rate budget is dropped, not queued",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        capacity = float(params["capacity_bit"])
        stored = capacity * float(params["initial_fill_ratio"])
        return {
            "stored_bit": stored,
            "buffer_capacity_bit": capacity,
            "fill_fraction": stored / capacity,
            "dropped_bit": 0.0,
            "drained_bit": 0.0,
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        capacity = state["buffer_capacity_bit"]
        produced = context.data_produced_bit
        incoming = min(produced, float(params["write_rate_bit_s"]) * context.dt_s)
        space = capacity - state["stored_bit"]
        written = min(incoming, space)
        dropped_step = (produced - incoming) + (incoming - written)
        state["stored_bit"] = state["stored_bit"] + written
        drained = min(float(params["read_rate_bit_s"]) * context.dt_s, state["stored_bit"])
        state["stored_bit"] = state["stored_bit"] - drained
        state["fill_fraction"] = state["stored_bit"] / capacity
        state["dropped_bit"] = state["dropped_bit"] + max(0.0, dropped_step)
        state["drained_bit"] = state["drained_bit"] + drained
        context.data_produced_bit = 0.0


class ComputeCapacity:
    """Reserved compute throughput for onboard autonomy; draws power when used."""

    key = "compute.capacity"
    label = "Onboard compute budget"
    kind = "compute"
    stage = STAGES["compute"]
    assumptions = (
        "throughput is reserved at the configured duty cycle regardless of demand",
        "power draw applies while the duty cycle is non-zero",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        duty = float(params["duty_cycle_ratio"])
        return {
            "throughput_hz": float(params["throughput_hz"]),
            "duty_cycle_fraction": duty,
            "utilization_fraction": duty,
        }

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        duty = float(params["duty_cycle_ratio"])
        state["duty_cycle_fraction"] = duty
        state["utilization_fraction"] = duty
        if duty > 0.0:
            context.power_draw_w += float(params["draw_w"])


class ClockTickSource:
    """Emits a deterministic tick event every ``interval_s`` (Day 25 ground work).

    Events are counted, not buffered: the cumulative count plus the next
    scheduled tick fully describe the source at any simulation time, so the
    outcome is a pure function of elapsed simulated time — an important
    property for restart determinism.
    """

    key = "event-source.clock-tick"
    label = "Clock tick event source"
    kind = "event-source"
    stage = STAGES["event-source"]
    assumptions = (
        "events are instantaneous and deterministic; real-time batching is out of scope",
    )

    def initial_state(self, params: Mapping[str, Any]) -> dict[str, Any]:
        interval = float(params["interval_s"])
        return {"tick_count": 0, "interval_s": interval, "next_tick_s": interval}

    def step(self, state: dict[str, Any], params: Mapping[str, Any], context: ComponentContext) -> None:
        while context.time_s >= state["next_tick_s"]:
            state["next_tick_s"] += state["interval_s"]
            state["tick_count"] += 1


# The default component mix. It exists so the visual demo is useful out of the
# box without forcing every scenario to spell out every field; a scenario
# overrides it either fleet-wide (SimulationConfig.components) or per satellite.
DEFAULT_COMPONENT_KEYS: tuple[str, ...] = (
    "event-source.clock-tick",
    "task.round-robin",
    "sensor.conical",
    "payload.imaging",
    "storage.buffer",
    "compute.capacity",
    "power.solar-battery",
)


# --- capability resolution and validation ------------------------------------------

def declared_components(config: Any, satellite: Any) -> list[Any]:
    """The ComponentConfig list in force for ``satellite`` (may be empty)."""
    own = getattr(satellite, "components", None)
    if own:
        return list(own)
    fleet = getattr(config, "components", None)
    if fleet:
        return list(fleet)
    return []


def validate_components(config: Any) -> None:
    """Check every declared component against the registries; raise ComponentError.

    Verified here: the component key is registered, it is not declared twice on
    one satellite, and every supplied parameter value exists in the Day 19
    registry for that component, has the right type and stays inside its bounds.
    """
    issues: list[dict[str, str]] = []
    for index, satellite in enumerate(config.satellites):
        seen: set[str] = set()
        for position, declared_component in enumerate(declared_components(config, satellite)):
            type_path = f"$.satellites[{index}].components[{position}].type"
            try:
                component(declared_component.type)
            except ComponentError as exc:
                issues.extend({**issue, "path": type_path} for issue in exc.issues)
            if declared_component.type in seen:
                issues.append({"path": type_path,
                               "message": f"component {declared_component.type!r} is declared more than once"})
            seen.add(declared_component.type)
            values = declared_component.parameters or {}
            issues.extend(builtin_registry().validate_values(
                declared_component.type, values,
                path=f"$.satellites[{index}].components[{position}].parameters"))
    if issues:
        raise ComponentError(issues)


# --- runtime state (the runner) ------------------------------------------------------

@dataclass
class SatelliteRuntime:
    """Effective parameters and live state for one satellite's component set."""

    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    state: dict[str, dict[str, Any]] = field(default_factory=dict)


def _stage_order(key: str) -> tuple[int, str]:
    model = component(key)
    return (getattr(model, "stage", 0), key)


def initial_runtime(config: Any) -> dict[str, SatelliteRuntime]:
    """Build per-satellite effective parameters and epoch component states."""
    runtime: dict[str, SatelliteRuntime] = {}
    for satellite in config.satellites:
        declared = declared_components(config, satellite)
        entry = SatelliteRuntime()
        # An empty declaration means the default reference mix applies.
        keys = [item.type for item in declared] if declared else list(DEFAULT_COMPONENT_KEYS)
        for key in keys:
            values = next(
                (item.parameters for item in declared if item.type == key), None
            ) if declared else {}
            entry.params[key] = effective_params(key, values)
            entry.state[key] = component(key).initial_state(entry.params[key])
        runtime[satellite.id] = entry
    return runtime


def _sunlit_for(position_km: Vector3, epoch_utc: str, time_s: float) -> float:
    return sunlit_fraction(position_km, sun_direction_eci(epoch_utc, time_s))


def positions_from_config(config: Any, time_s: float) -> dict[str, Vector3]:
    """Orbital position of every satellite at ``time_s`` (ECI, km).

    Imports orbit math lazily so the component layer never depends on the
    snapshot builder; dynamics selection goes through the registry exactly as
    the Day 15 loop does.
    """
    from .dynamics import DEFAULT_MODEL_KEY, dynamics_model

    model = dynamics_model(config.dynamics_model or DEFAULT_MODEL_KEY)
    return {sat.id: model.state_at(sat.orbit, time_s)[0] for sat in config.satellites}


def advance_runtime(config: Any, runtime: Mapping[str, SatelliteRuntime], *,
                    time_s: float, dt_s: float,
                    positions: Mapping[str, Vector3] | None = None) -> None:
    """Advance every satellite's component pipeline by ``dt_s`` in place."""
    if dt_s <= 0.0:
        return
    resolved = positions if positions is not None else positions_from_config(config, time_s)
    for satellite in config.satellites:
        entry = runtime.get(satellite.id)
        if entry is None or not entry.state:
            continue
        position = resolved.get(satellite.id, (0.0, 0.0, 0.0))
        context = ComponentContext(
            epoch_utc=config.epoch_utc,
            time_s=time_s,
            dt_s=dt_s,
            position_km=position,
            sunlit_ratio=_sunlit_for(position, config.epoch_utc, time_s),
        )
        for key in sorted(entry.state, key=_stage_order):
            component(key).step(entry.state[key], entry.params[key], context)


def runtime_snapshot(config: Any, runtime: Mapping[str, SatelliteRuntime]) -> dict[str, list[dict[str, Any]]]:
    """Snapshot-friendly per-satellite component state lists."""
    out: dict[str, list[dict[str, Any]]] = {}
    for satellite in config.satellites:
        entry = runtime.get(satellite.id)
        if entry is None or not entry.state:
            continue
        out[satellite.id] = [
            {"type": key, "state": dict(entry.state[key])}
            for key in sorted(entry.state, key=_stage_order)
        ]
    return out


INTEGRATION_MAX_SUBSTEPS = 2000


def integrated_states(config: Any, time_s: float) -> dict[str, SatelliteRuntime]:
    """Rebuild the component state at ``time_s`` from scratch.

    Integrates in one-second sub-steps — the same step the running service
    uses — so a rebuild at ``time_s`` matches an incremental advance exactly
    (state and floats alike), and stays deterministic in ``time_s`` alone. The
    step grows with the horizon (a documented limitation: energy bookkeeping
    accuracy degrades on very long one-shot rebuilds); the running service
    advances incrementally instead and never needs this helper.
    """
    runtime = initial_runtime(config)
    if time_s <= 0.0:
        return runtime
    steps = min(INTEGRATION_MAX_SUBSTEPS, max(1, math.ceil(time_s / 1.0)))
    dt = time_s / steps
    positions = positions_from_config(config, time_s)
    for index in range(steps):
        chunk = min(dt, 1.0)
        advance_runtime(config, runtime, time_s=(index + 1) * chunk, dt_s=chunk,
                        positions=positions)
    return runtime


def states_payload() -> dict[str, Any]:
    """Machine-readable component registry description for the API and tests."""
    return {
        "keys": list(registered_components()),
        "kinds": list(KINDS),
        "stages": dict(STAGES),
        "default_keys": list(DEFAULT_COMPONENT_KEYS),
        "components": describe_components(),
    }
