"""Day 16: physical-domain validation of orbital inputs.

The contract schema pins representation (a number, a range) but not physics: a
semi-major axis of 1,000 km with an eccentricity of 0.5 is a well-formed payload
that describes an orbit through the planet. This module answers the second
question — is the orbit a closed, above-surface ellipse? — before anything is
propagated, and reports the offending field path so a client can highlight it.

Boundary rule: an orbit must clear the WGS-84 equatorial surface at perigee.
Grazing orbits (perigee altitude exactly 0) are accepted; intersecting ones are
not. That is a deliberate simplification: atmospheric drag would remove a grazing
orbit within a fraction of a revolution, and modelling drag is not part of this
fidelity level.

Every numeric field's unit is declared once in :data:`ORBIT_FIELD_UNITS` and
checked against the unit registry, so a renamed field can not silently claim a
new unit.
"""

from __future__ import annotations

import math
from typing import Any

from .contract import OrbitElements
from .frames import EARTH_EQUATORIAL_RADIUS_KM
from .orbit import MU_EARTH_KM3_S2
from .units import key_matches_unit, unit_kind

# Field -> declared unit. The name suffix and the registry must agree.
ORBIT_FIELD_UNITS: dict[str, str] = {
    "semi_major_axis_km": "km",
    "eccentricity": "1",
    "inclination_deg": "deg",
    "raan_deg": "deg",
    "argument_of_perigee_deg": "deg",
    "true_anomaly_deg": "deg",
}

# Eccentricities this model can propagate without the Kepler solver losing the
# perigee pass. The solver itself converges well past this, but the closed-form
# check against a numerical reference degrades first; see ``dynamics`` limits.
MAX_SUPPORTED_ECCENTRICITY = 0.995


def orbit_issues(elements: OrbitElements) -> list[dict[str, str]]:
    """Physical problems with ``elements``; ``field`` is relative to the elements.

    An empty list means the orbit is a closed ellipse that clears the surface.
    """
    issues: list[dict[str, str]] = []

    def issue(field: str, message: str) -> None:
        issues.append({"field": field, "message": message})

    a = elements.semi_major_axis_km
    e = elements.eccentricity

    for field, value in (
        ("semi_major_axis_km", a),
        ("eccentricity", e),
        ("inclination_deg", elements.inclination_deg),
        ("raan_deg", elements.raan_deg),
        ("argument_of_perigee_deg", elements.argument_of_perigee_deg),
        ("true_anomaly_deg", elements.true_anomaly_deg),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            issue(field, f"{field} must be a finite number, got {value!r}")

    if issues:
        return issues

    if a <= EARTH_EQUATORIAL_RADIUS_KM:
        issue("semi_major_axis_km",
              f"semi-major axis {a:g} km must exceed Earth's equatorial radius "
              f"{EARTH_EQUATORIAL_RADIUS_KM:g} km")
        return issues

    if e < 0.0:
        issue("eccentricity", f"eccentricity must be >= 0, got {e:g}")
    elif e >= 1.0:
        issue("eccentricity", f"eccentricity must be < 1 for a closed orbit, got {e:g}")
    elif e > MAX_SUPPORTED_ECCENTRICITY:
        issue("eccentricity",
              f"eccentricity {e:g} exceeds the supported maximum {MAX_SUPPORTED_ECCENTRICITY:g} "
              f"for the analytic propagator")

    if not 0.0 <= elements.inclination_deg <= 180.0:
        issue("inclination_deg",
              f"inclination must be within [0, 180] degrees, got {elements.inclination_deg:g}")

    if 0.0 <= e < 1.0:
        perigee_km = a * (1.0 - e)
        if perigee_km < EARTH_EQUATORIAL_RADIUS_KM:
            issue("eccentricity" if e > 0.0 else "semi_major_axis_km",
                  f"perigee radius {perigee_km:g} km is below Earth's equatorial surface "
                  f"({EARTH_EQUATORIAL_RADIUS_KM:g} km): a = {a:g} km, e = {e:g}")

    # A hyperbolic excess would already have been caught by e >= 1. This is the
    # numerical guard: the specific orbital energy must stay negative and finite.
    energy = -MU_EARTH_KM3_S2 / (2.0 * a)
    if not math.isfinite(energy) or energy >= 0.0:
        issue("semi_major_axis_km", f"specific orbital energy {energy:g} km^2/s^2 is not bound")

    return issues


def validate_elements(elements: OrbitElements, path_prefix: str = "$.orbit") -> list[dict[str, str]]:
    """Issues in the contract's ``{path, message}`` shape, with full field paths."""
    return [{"path": f"{path_prefix}.{item['field']}", "message": item["message"]}
            for item in orbit_issues(elements)]


def derived_geometry(elements: OrbitElements) -> dict[str, float]:
    """Useful quantities derived from the elements, in contract units."""
    a, e = elements.semi_major_axis_km, elements.eccentricity
    return {
        "perigee_radius_km": a * (1.0 - e),
        "apogee_radius_km": a * (1.0 + e),
        "perigee_altitude_km": a * (1.0 - e) - EARTH_EQUATORIAL_RADIUS_KM,
        "apogee_altitude_km": a * (1.0 + e) - EARTH_EQUATORIAL_RADIUS_KM,
        "semi_minor_axis_km": a * math.sqrt(max(0.0, 1.0 - e * e)),
        "specific_energy_km2_s2": -MU_EARTH_KM3_S2 / (2.0 * a),
    }


def field_unit_issues() -> list[dict[str, str]]:
    """Self-check: the declared unit of every field matches its name and kind."""
    issues: list[dict[str, str]] = []
    for field, unit in ORBIT_FIELD_UNITS.items():
        if unit != "1" and not key_matches_unit(field, unit):
            issues.append({"path": field,
                           "message": f"field name does not end with the slug of its unit {unit!r}"})
        if unit_kind(unit) not in ("ratio", "length", "angle"):
            issues.append({"path": field, "message": f"unexpected unit kind for an orbital element: {unit!r}"})
    return issues


def orbit_field_payload() -> dict[str, Any]:
    """Machine-readable field/unit table for the parameter registry and tests."""
    return {
        "fields": {field: {"unit": unit, "kind": unit_kind(unit)} for field, unit in ORBIT_FIELD_UNITS.items()},
        "surface_radius_km": EARTH_EQUATORIAL_RADIUS_KM,
        "max_supported_eccentricity": MAX_SUPPORTED_ECCENTRICITY,
    }
