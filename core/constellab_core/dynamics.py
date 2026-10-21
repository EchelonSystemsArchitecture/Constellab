"""Day 15: registered orbital dynamics components.

The simulation loop asks for a model **by key**; it never branches on which
fidelity level a scenario uses. Adding a propagator therefore means registering
another :class:`DynamicsModel`, not editing the main loop, the parser or the
renderer.

The single registered model today is ``keplerian-two-body``: a closed Keplerian
orbit propagated analytically from classical elements. Perturbations (J2, drag,
third-body, solar radiation pressure) are deliberately **not** modelled and are
reported as assumptions so the UI can keep the limitation visible.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from . import orbit
from .contract import OrbitElements, Vector3

DEFAULT_MODEL_KEY = "keplerian-two-body"


@runtime_checkable
class DynamicsModel(Protocol):
    """A propagator the simulation loop can select by key."""

    key: str
    label: str
    assumptions: tuple[str, ...]

    def state_at(self, elements: OrbitElements, time_s: float) -> tuple[Vector3, Vector3]:
        """ECI position (km) and velocity (km/s) at ``time_s`` seconds since epoch."""

    def period_s(self, elements: OrbitElements) -> float:
        """One full orbital period in simulated seconds."""


class KeplerianTwoBody:
    """Analytic two-body Kepler propagation from classical orbital elements."""

    key = DEFAULT_MODEL_KEY
    label = "Keplerian two-body"
    assumptions = (
        "point-mass Earth, mu = 398600.4418 km^3/s^2",
        "closed Keplerian orbit from classical elements",
        "no perturbations (J2, drag, third body, solar radiation pressure) and no manoeuvres",
        "ECI frame is inertial and fixed at the scenario epoch; Earth rotation is a separate transform",
    )

    def state_at(self, elements: OrbitElements, time_s: float) -> tuple[Vector3, Vector3]:
        return orbit.state_from_elements_at_time(elements, time_s)

    def period_s(self, elements: OrbitElements) -> float:
        return orbit.orbital_period_s(elements)


_REGISTRY: dict[str, DynamicsModel] = {}


def register_model(model: DynamicsModel) -> DynamicsModel:
    """Register a dynamics component under its own key (idempotent replacement)."""
    key = getattr(model, "key", None)
    if not isinstance(key, str) or not key:
        raise ValueError("a dynamics model must declare a non-empty string key")
    _REGISTRY[key] = model
    return model


def unregister_model(key: str) -> DynamicsModel | None:
    """Remove a model from the registry (used by tests and optional plugins)."""
    return _REGISTRY.pop(key, None)


def registered_models() -> dict[str, DynamicsModel]:
    return dict(_REGISTRY)


def dynamics_model(key: str | None = None) -> DynamicsModel:
    """Return the registered model for ``key`` (or the default when omitted)."""
    resolved = key or DEFAULT_MODEL_KEY
    try:
        return _REGISTRY[resolved]
    except KeyError:
        raise KeyError(f"unknown dynamics model {resolved!r}") from None


def describe_models() -> list[dict[str, object]]:
    """Machine-readable registry description, in stable key order."""
    return [
        {"key": model.key, "label": model.label, "assumptions": list(model.assumptions)}
        for _, model in sorted(_REGISTRY.items())
    ]


register_model(KeplerianTwoBody())
