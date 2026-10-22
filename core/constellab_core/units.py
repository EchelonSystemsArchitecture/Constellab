"""Day 16: one unit registry for every physical quantity in the core.

Names alone do not carry units, so a field called ``altitude`` can be metres in
one producer and kilometres in another. This module makes the unit explicit:
every quantity kind has one canonical unit, conversions happen only through
:func:`convert`, and an incompatible pair raises :class:`UnitError` naming both
units and the kind each one measures.

The canonical units are the ones the simulation core already uses where they
exist (km for orbital state, degrees for elements, seconds for clocks). Inside
new code prefer SI: m, m/s, rad, s, kg, W, J, bit. The contract keeps its
published units, so conversion at the boundary is explicit instead of assumed.

Naming convention used by the parameter registry (Day 19) and component state
keys: a numeric key ends with ``_<unit_slug>``, e.g. ``array_area_m2``,
``base_load_w``, ``battery_capacity_j``. :func:`unit_slug` is the single source
for those suffixes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class UnitError(ValueError):
    """A unit is unknown, or two units measure different quantities."""

    def __init__(self, message: str, *, kind: str | None = None, unit: str | None = None,
                 available: tuple[str, ...] = ()):
        self.kind = kind
        self.unit = unit
        self.available = available
        super().__init__(message)

    def to_issue(self, path: str = "$") -> dict[str, str]:
        """Field-path diagnostic in the same shape the contract validator uses."""
        return {"path": path, "message": str(self)}


# symbol -> (kind, factor to the kind's canonical unit, spelling aliases)
_UNITS: dict[str, tuple[str, float, tuple[str, ...]]] = {
    # length (canonical: m)
    "m": ("length", 1.0, ("metre", "metres", "meter", "meters")),
    "km": ("length", 1000.0, ("kilometre", "kilometres", "kilometer", "kilometers")),
    "cm": ("length", 0.01, ()),
    "mm": ("length", 0.001, ()),
    "mi": ("length", 1609.344, ("mile", "miles")),
    # time (canonical: s)
    "s": ("time", 1.0, ("sec", "secs", "second", "seconds")),
    "ms": ("time", 0.001, ("millisecond", "milliseconds")),
    "min": ("time", 60.0, ("minute", "minutes")),
    "h": ("time", 3600.0, ("hr", "hrs", "hour", "hours")),
    "day": ("time", 86400.0, ("d", "days")),
    # angle (canonical: rad)
    "rad": ("angle", 1.0, ("radian", "radians")),
    "deg": ("angle", math.pi / 180.0, ("degree", "degrees", "°", "º")),
    "arcsec": ("angle", math.pi / (180.0 * 3600.0), ("arcsecond", "arcseconds")),
    # velocity (canonical: m/s)
    "m/s": ("velocity", 1.0, ("mps",)),
    "km/s": ("velocity", 1000.0, ("kmps", "km/s")),
    "km/h": ("velocity", 1000.0 / 3600.0, ()),
    # mass (canonical: kg)
    "kg": ("mass", 1.0, ("kilogram", "kilograms")),
    "g": ("mass", 0.001, ("gram", "grams")),
    # area (canonical: m2)
    "m2": ("area", 1.0, ("m^2", "m²")),
    "cm2": ("area", 1e-4, ("cm^2", "cm²")),
    "km2": ("area", 1e6, ("km^2", "km²")),
    # power (canonical: W)
    "W": ("power", 1.0, ("watt", "watts")),
    "kW": ("power", 1000.0, ("kilowatt", "kilowatts")),
    "mW": ("power", 0.001, ("milliwatt", "milliwatts")),
    # energy (canonical: J)
    "J": ("energy", 1.0, ("joule", "joules")),
    "Wh": ("energy", 3600.0, ("watt-hour", "watt-hours")),
    "kWh": ("energy", 3_600_000.0, ()),
    # data (canonical: bit)
    "bit": ("data", 1.0, ("bits",)),
    "kbit": ("data", 1000.0, ()),
    "Mbit": ("data", 1e6, ()),
    "Gbit": ("data", 1e9, ()),
    "byte": ("data", 8.0, ("bytes", "B")),
    "kB": ("data", 8000.0, ()),
    "MB": ("data", 8e6, ()),
    "KiB": ("data", 8192.0, ()),
    "MiB": ("data", 8.0 * 1024.0 ** 2, ()),
    # data rate (canonical: bit/s)
    "bit/s": ("data_rate", 1.0, ("bps",)),
    "kbit/s": ("data_rate", 1000.0, ("kbps",)),
    "Mbit/s": ("data_rate", 1e6, ("Mbps",)),
    "kB/s": ("data_rate", 8000.0, ("KBps",)),
    # frequency (canonical: Hz)
    "Hz": ("frequency", 1.0, ("hertz",)),
    "kHz": ("frequency", 1000.0, ()),
    # dimensionless
    "1": ("ratio", 1.0, ("ratio", "fraction")),
    "%": ("ratio", 0.01, ("percent", "pct")),
}

# Preferred spelling and canonical unit per kind, in a stable order.
_CANONICAL: dict[str, str] = {}
for _symbol, (_kind, _factor, _aliases) in _UNITS.items():
    if _factor == 1.0 and _kind not in _CANONICAL:
        _CANONICAL[_kind] = _symbol
# "1" must win over "%" for the ratio kind (both have factor 1.0 only for "1").
_CANONICAL["ratio"] = "1"

_LOOKUP: dict[str, str] = {}
for _symbol, (_kind, _factor, _aliases) in _UNITS.items():
    _LOOKUP[_symbol] = _symbol
    for _alias in _aliases:
        # Exact match first at lookup time, but store the lower-case spelling so
        # "KM" and "Kilometres" resolve without making symbol lookup case-blind.
        _LOOKUP.setdefault(_alias.lower(), _symbol)


def normalize_unit(unit: str) -> str:
    """Return the registry's spelling of ``unit``.

    Symbols are matched exactly first (``m`` and ``M`` are different things),
    then case-insensitively for spelling aliases (``KM`` -> ``km``).
    """
    if not isinstance(unit, str) or not unit.strip():
        raise UnitError("unit must be a non-empty string", unit=str(unit))
    candidate = unit.strip()
    if candidate in _UNITS:
        return candidate
    resolved = _LOOKUP.get(candidate.lower())
    if resolved is None:
        raise UnitError(
            f"unknown unit {candidate!r}; known units: {', '.join(sorted(_UNITS))}",
            unit=candidate,
            available=tuple(sorted(_UNITS)),
        )
    return resolved


def unit_kind(unit: str) -> str:
    """Quantity kind a unit measures (length, time, power, ...)."""
    return _UNITS[normalize_unit(unit)][0]


def canonical_unit(kind: str) -> str:
    try:
        return _CANONICAL[kind]
    except KeyError:
        raise UnitError(f"unknown quantity kind {kind!r}; known kinds: {', '.join(sorted(_CANONICAL))}",
                        kind=kind) from None


def units_for(kind: str) -> tuple[str, ...]:
    """Every registered unit that measures ``kind``, canonical first."""
    canonical = canonical_unit(kind)
    return tuple([canonical] + sorted(u for u, spec in _UNITS.items() if spec[0] == kind and u != canonical))


def _factor(unit: str) -> float:
    return _UNITS[normalize_unit(unit)][1]


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between two units that measure the same quantity.

    Raises :class:`UnitError` when either unit is unknown or the units are
    incompatible, e.g. ``km`` (length) to ``s`` (time). The message names both
    kinds, because "cannot convert" without them is not actionable.
    """
    source, target = normalize_unit(from_unit), normalize_unit(to_unit)
    source_kind, target_kind = _UNITS[source][0], _UNITS[target][0]
    if source_kind != target_kind:
        raise UnitError(
            f"incompatible units: {source!r} is {source_kind}, {target!r} is {target_kind}; "
            f"use one of {', '.join(units_for(source_kind))}",
            kind=source_kind,
            unit=source,
            available=units_for(source_kind),
        )
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise UnitError(f"value for {source!r} must be numeric, got {type(value).__name__}") from None
    if not math.isfinite(numeric):
        raise UnitError(f"value for {source!r} must be finite, got {numeric!r}")
    return numeric * _factor(source) / _factor(target)


def to_canonical(value: float, unit: str) -> float:
    return convert(value, unit, canonical_unit(unit_kind(unit)))


def from_canonical(value: float, unit: str) -> float:
    return convert(value, canonical_unit(unit_kind(unit)), unit)


def unit_slug(unit: str) -> str:
    """Suffix used in field and parameter keys, e.g. ``km/s`` -> ``km_s``.

    The mapping is mechanical so a key can never disagree with the unit it
    claims: ``unit_slug(unit)`` lower-cases the symbol and replaces ``/`` with
    ``_``. Ratios use ``ratio`` and percent uses ``pct``.
    """
    symbol = normalize_unit(unit)
    if symbol == "1":
        return "ratio"
    slug = symbol.lower().replace("/", "_").replace("^", "").replace("²", "2")
    return slug.replace("%", "pct")


def key_matches_unit(key: str, unit: str) -> bool:
    """True when a numeric field key ends with its unit's slug."""
    return key.endswith("_" + unit_slug(unit))


def format_quantity(value: float, unit: str, digits: int = 3) -> str:
    """Format a value with its unit, rounding only for display."""
    symbol = normalize_unit(unit)
    if not math.isfinite(float(value)):
        raise UnitError(f"cannot format a non-finite value ({value!r})", unit=symbol)
    number = f"{float(value):,.{digits}f}"
    if symbol == "1":
        return number
    if symbol == "%":
        return f"{number}%"
    return f"{number} {symbol}"


@dataclass(frozen=True)
class Quantity:
    """A number with an explicit unit, convertible but never silently mixed."""

    value: float
    unit: str

    def __post_init__(self) -> None:
        # Validate eagerly so a bad unit fails where it was written.
        normalize_unit(self.unit)
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise UnitError(f"Quantity value must be numeric, got {type(self.value).__name__}")
        if not math.isfinite(float(self.value)):
            raise UnitError(f"Quantity value must be finite, got {self.value!r}")

    @property
    def kind(self) -> str:
        return unit_kind(self.unit)

    @property
    def canonical(self) -> float:
        return to_canonical(self.value, self.unit)

    def to(self, unit: str) -> "Quantity":
        return Quantity(convert(self.value, self.unit, unit), unit)

    def format(self, digits: int = 3) -> str:
        return format_quantity(self.value, self.unit, digits)

    def __str__(self) -> str:
        return self.format()

    def __add__(self, other: "Quantity") -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        return Quantity(self.value + other.to(self.unit).value, self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        return Quantity(self.value - other.to(self.unit).value, self.unit)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        return self.canonical == other.canonical

    def __hash__(self) -> int:
        return hash((self.kind, self.canonical))


def registry_payload() -> dict[str, Any]:
    """Machine-readable unit table for the API and tests."""
    return {
        "canonical": {kind: unit for kind, unit in sorted(_CANONICAL.items())},
        "units": {
            symbol: {"kind": kind, "to_canonical": factor, "aliases": list(aliases),
                     "slug": unit_slug(symbol)}
            for symbol, (kind, factor, aliases) in sorted(_UNITS.items())
        },
    }
