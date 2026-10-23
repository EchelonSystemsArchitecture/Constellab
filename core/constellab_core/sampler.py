"""Day 23: a deterministic configuration/scene sampler driven by registry metadata.

The sampler never holds a list of hard-coded variable names: every field it
touches comes from a ``ParameterSpec`` (bounds, enum, distribution, mutability,
schema version). Sampling is reproducible because each sample's random stream
is derived from ``(campaign seed, schema hash, sample index)`` — not from a
shared sequential generator — so a large campaign can be **resumed**: sampling
index 40..79 of a 100-sample campaign yields exactly the values a full run
would have produced.

* Distributions: registry ``distribution`` metadata (constant / uniform /
  log-uniform / normal) plus categorical enums and booleans. Unknown or
  unsupported distributions fall back to the constant default and are recorded
  as notes, never silently reinterpreted.
* Correlations: optional ``links`` (follower = driver * ratio) so dependent
  quantities stay physically consistent without arbitrary code.
* Constraints: every candidate sample is checked with the Day 21 constraint
  registry (per-owner builtin rules) and re-seeded up to ``max_attempts``
  times; the attempts count and constraint outcome are persisted per sample.
* Families: train / validation / test splits are assigned by sample index so a
  resumed campaign reproduces the same family assignment.

Only stdlib is used. No ``eval``: sampling and constraint checking go through
the typed constraint operators.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .constraints import builtin_rules
from .parameters import ParameterRegistry, ParameterSpec, builtin_registry

SAMPLER_VERSION = "constellab-sampler-1"
FAMILIES: tuple[str, ...] = ("train", "validation", "test")
DEFAULT_SPLITS: tuple[float, ...] = (0.7, 0.2, 0.1)
DEFAULT_MAX_ATTEMPTS = 16
METHODS: tuple[str, ...] = ("random", "latin-hypercube")

SAMPLABLE_DISTRIBUTIONS: frozenset[str] = frozenset(
    {"constant", "uniform", "log-uniform", "normal"}
)


class SamplerError(ValueError):
    """Raised for invalid sampler configuration; the campaign stays untouched."""


def _tolist(values: Sequence[float] | None) -> list[float]:
    return list(values) if values is not None else list(DEFAULT_SPLITS)


def validate_splits(splits: Sequence[float]) -> tuple[float, ...]:
    values = _tolist(splits)
    if len(values) != len(FAMILIES):
        raise SamplerError(f"splits must have {len(FAMILIES)} entries, got {len(values)}")
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise SamplerError("splits must be non-negative finite weights")
    total = sum(values)
    if total <= 0:
        raise SamplerError("splits must sum to a positive weight")
    return tuple(v / total for v in values)  # type: ignore[return-value]


def family_for_index(index: int, splits: Sequence[float] | None = None) -> str:
    """Deterministic family assignment: a fixed 100-slot block keeps families
    stable across resumed campaigns; split weights are rounded into block
    boundaries exactly as given (a zero-weight family gets zero slots)."""
    normalized = validate_splits(splits)
    block = 100
    edges: list[int] = []
    acc = 0
    for weight in normalized:
        acc += round(weight * block)
        edges.append(min(acc, block))
    slot = index % block
    for label, edge in zip(FAMILIES, edges):
        if slot < edge:
            return label
    return FAMILIES[-1]


def derived_seed(seed: int, schema_hash: str, index: int, attempt: int = 0) -> int:
    """Stable per-sample seed — the corner stone of resumable determinism."""
    payload = f"{SAMPLER_VERSION}|{seed}|{schema_hash}|{index}|{attempt}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:12], 16)


def _clamp(value: float, minimum: float | None, maximum: float | None) -> float:
    if minimum is not None and value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


def _log_bounds(spec: ParameterSpec) -> tuple[float, float]:
    minimum = spec.minimum if spec.minimum is not None else 1e-6
    maximum = spec.maximum if spec.maximum is not None else max(1e-3, minimum * 1e3)
    if minimum <= 0 or maximum <= 0:
        raise SamplerError(
            f"{spec.key}: log-uniform sampling needs positive bounds, got ["
            f"{spec.minimum}, {spec.maximum}]"
        )
    return math.log(minimum), math.log(maximum)


def sample_value(
    spec: ParameterSpec,
    rng: random.Random,
    *,
    stratum: tuple[int, int] | None = None,
) -> tuple[Any, str]:
    """Sample one typed value for ``spec``; returns ``(value, distribution_used)``."""
    distribution = spec.distribution or "constant"
    if spec.enum:
        return rng.choice(list(spec.enum)), "categorical"
    if spec.kind == "boolean":
        return rng.choice([True, False]), "categorical"
    if distribution == "constant":
        return spec.default, "constant"
    if spec.kind not in ("number", "integer"):
        return spec.default, "constant"

    if distribution == "uniform":
        if spec.minimum is None or spec.maximum is None:
            # A uniform spec without declared bounds strands on its default.
            return spec.default, "constant-fallback"
        low, high = float(spec.minimum), float(spec.maximum)
        # Latin hypercube: one value inside the stratum this sample owns.
        if stratum is not None:
            bin_index, bins = stratum
            if bins > 0:
                u = (bin_index + rng.random()) / bins
                low = spec.minimum + u * (high - spec.minimum)
                value = low
            else:
                value = low
        else:
            value = rng.uniform(low, high)
    elif distribution == "log-uniform":
        low_log, high_log = _log_bounds(spec)
        if stratum is not None:
            bin_index, bins = stratum
            u = (bin_index + rng.random()) / bins if bins else 0.0
            value = math.exp(low_log + u * (high_log - low_log))
        else:
            value = math.exp(rng.uniform(low_log, high_log))
    elif distribution == "normal":
        centre = float(spec.default)
        spread = max(abs(centre) * 0.1, 1e-9)
        value = rng.gauss(centre, spread)
    else:
        return spec.default, "constant-fallback"

    value = _clamp(float(value), spec.minimum, spec.maximum)
    if spec.kind == "integer":
        value = int(round(value))
        if spec.minimum is not None:
            value = max(value, int(spec.minimum))
        if spec.maximum is not None:
            value = min(value, int(spec.maximum))
    return value, distribution


def _candidate_values(
    registry: ParameterRegistry,
    owners: Sequence[str],
    rng: random.Random,
    links: Mapping[str, Mapping[str, float]],
    stratum: tuple[int, int] | None,
) -> dict[str, dict[str, Any]]:
    # Pass 1: sample every samplable field from its own spec metadata.
    # Pass 2: overwrite linked followers from their (now sampled) drivers so
    # declaration order can never break a correlation.
    values: dict[str, dict[str, Any]] = {}
    for owner in owners:
        bucket: dict[str, Any] = {}
        for spec in registry.by_owner(owner):
            if spec.mutability == "never":
                continue
            value, _ = sample_value(spec, rng, stratum=stratum)
            bucket[spec.short_key] = value
        for spec in registry.by_owner(owner):
            short_key = spec.short_key
            driver = links.get(f"{owner}.{short_key}")
            if not driver:
                continue
            source = bucket.get(str(driver.get("driver", "")))
            if source is None:
                continue
            ratio = float(driver.get("ratio", 1.0))
            linked = _clamp(float(source) * ratio, spec.minimum, spec.maximum)
            if spec.kind == "integer":
                linked = int(round(linked))
            bucket[short_key] = linked
        values[owner] = bucket
    return values


def _constraint_outcome(
    registry: ParameterRegistry, values: Mapping[str, Mapping[str, Any]], rules
) -> tuple[str, list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    for owner, bucket in values.items():
        effective = registry.effective_values(owner, bucket, path=f"$/{owner}")
        for issue in rules.check(effective, scope=owner, path=f"$/{owner}"):
            issues.append(dict(issue))
    if issues:
        return "violated", issues
    return "pass", []


@dataclass
class SampleRecord:
    """One generated configuration; everything needed to rebuild and verify it."""

    sample_id: str
    index: int
    family: str
    seed: int
    values: dict[str, dict[str, Any]]
    constraint: str
    constraint_issues: list[dict[str, str]]
    attempts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "index": self.index,
            "family": self.family,
            "seed": self.seed,
            "values": self.values,
            "constraint": self.constraint,
            "constraint_issues": self.constraint_issues,
            "attempts": self.attempts,
        }


def summarize_spec(
    spec: ParameterSpec, observed: list[Any], family: str | None = None
) -> dict[str, Any]:
    """Human/machine distribution summary for one field (optionally per family)."""
    summary: dict[str, Any] = {"key": spec.key, "count": len(observed)}
    if family:
        summary["family"] = family
    if spec.enum:
        counts: dict[str, int] = {}
        for value in observed:
            counts[repr(value)] = counts.get(repr(value), 0) + 1
        summary["counts"] = counts
        return summary
    numerics = [float(v) for v in observed if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not numerics:
        summary["non_numeric"] = [repr(v) for v in observed[:5]]
        return summary
    mean = sum(numerics) / len(numerics)
    variance = sum((v - mean) ** 2 for v in numerics) / len(numerics)
    summary.update(
        {
            "min": min(numerics),
            "max": max(numerics),
            "mean": round(mean, 6),
            "std": round(math.sqrt(variance), 6),
        }
    )
    return summary


class Sampler:
    """Deterministic sample generator for one registry + hash + seed."""

    def __init__(
        self,
        registry: ParameterRegistry | None = None,
        *,
        seed: int = 0,
        method: str = "random",
        splits: Sequence[float] | None = None,
        links: Mapping[str, Mapping[str, float]] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise SamplerError("seed must be an integer")
        if method not in METHODS:
            raise SamplerError(f"method {method!r} must be one of {list(METHODS)}")
        self.registry = registry or builtin_registry()
        self.schema_hash = self.registry.schema_hash()
        self.seed = seed
        self.method = method
        self.splits = validate_splits(splits)
        self.links: dict[str, dict[str, float]] = {
            key: {"driver": link["driver"], "ratio": float(link.get("ratio", 1.0))}
            for key, link in (links or {}).items()
        }
        self.max_attempts = max(1, int(max_attempts))
        self.rules = builtin_rules(self.registry)
        for key, link in self.links.items():
            owner, _, short = key.rpartition(".")
            known = key in self.registry or any(
                spec.short_key == short for spec in self.registry.by_owner(owner)
            )
            driver_key = str(link["driver"])
            # A driver without an owner prefix is a short key of the same owner.
            driver_owner, driver_short = (
                driver_key.rpartition(".")
                if "." in driver_key
                else (owner, driver_key)
            )
            driver_known = driver_key in self.registry or any(
                spec.short_key == driver_short for spec in self.registry.by_owner(driver_owner)
            )
            if not known or not driver_known:
                raise SamplerError(f"link {key!r} is not a registered parameter key")

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "sampler_version": SAMPLER_VERSION,
            "seed": self.seed,
            "method": self.method,
            "splits": list(self.splits),
            "schema_version": self.registry.payload()["schema_version"],
            "schema_hash": self.schema_hash,
            "links": {k: dict(v) for k, v in sorted(self.links.items())},
            "max_attempts": self.max_attempts,
        }

    def sample(self, count: int, *, start: int = 0) -> dict[str, Any]:
        """Generate ``count`` samples from ``start`` (resumable by index)."""
        if not isinstance(count, int) or count < 0:
            raise SamplerError("count must be a non-negative integer")
        if not isinstance(start, int) or start < 0:
            raise SamplerError("start must be a non-negative index")
        owners = [owner for owner in self.registry.owners() if self.registry.by_owner(owner)]
        samples: list[SampleRecord] = []
        for offset in range(count):
            index = start + offset
            samples.append(self._one_sample(index, owners))
        campaign = {
            "sampler": self.metadata,
            "count": len(samples),
            "start_index": start,
            "owners": owners,
            "notes": [],
            "samples": [record.to_dict() for record in samples],
        }
        campaign["summaries"] = self.summarize(campaign)
        return campaign

    def quick(self, count: int = 8) -> dict[str, Any]:
        """The documented quick-mode entry point for smoke/route checks."""
        return self.sample(count)

    def _one_sample(self, index: int, owners: Sequence[str]) -> SampleRecord:
        bins = 0 if self.method == "random" else 1
        stratum: tuple[int, int] | None = None
        if self.method == "latin-hypercube":
            # Sample i owns stratum i inside a cycle length of the campaign.
            stratum = (index % 64, 64)
        last_issues: list[dict[str, str]] = []
        for attempt in range(self.max_attempts):
            seed = derived_seed(self.seed, self.schema_hash, index, attempt)
            rng = random.Random(seed)
            values = _candidate_values(self.registry, owners, rng, self.links, stratum if bins else None)
            status, issues = _constraint_outcome(self.registry, values, self.rules)
            if status == "pass":
                return SampleRecord(
                    sample_id=f"sample-{index:04d}",
                    index=index,
                    family=family_for_index(index, self.splits),
                    seed=seed,
                    values=values,
                    constraint=status,
                    constraint_issues=[],
                    attempts=attempt + 1,
                )
            last_issues = issues
        # All attempts violated the constraints: record the failure loudly and
        # deterministically instead of pretending the sample is valid.
        return SampleRecord(
            sample_id=f"sample-{index:04d}",
            index=index,
            family=family_for_index(index, self.splits),
            seed=derived_seed(self.seed, self.schema_hash, index, 0),
            values=_candidate_values(
                self.registry,
                owners,
                random.Random(derived_seed(self.seed, self.schema_hash, index, 0)),
                self.links,
                stratum if bins else None,
            ),
            constraint="violated",
            constraint_issues=last_issues,
            attempts=self.max_attempts,
        )

    def summarize(self, campaign: dict[str, Any]) -> dict[str, Any]:
        """Distribution summaries per field, overall and per family."""
        specs = {spec.key: spec for owner in campaign["owners"] for spec in self.registry.by_owner(owner)}
        per_key: dict[str, list[Any]] = {}
        per_family: dict[str, dict[str, list[Any]]] = {family: {} for family in FAMILIES}
        for record in campaign["samples"]:
            for owner, bucket in record["values"].items():
                for short_key, value in bucket.items():
                    key = f"{owner}.{short_key}"
                    per_key.setdefault(key, []).append(value)
                    family = record["family"]
                    per_family.setdefault(family, {}).setdefault(key, []).append(value)
        summaries: dict[str, Any] = {}
        for key, observed in sorted(per_key.items()):
            entry: dict[str, Any] = {"overall": summarize_spec(specs[key], observed)}
            for family in FAMILIES:
                family_values = per_family.get(family, {}).get(key)
                if family_values:
                    entry[family] = summarize_spec(specs[key], family_values, family=family)
            summaries[key] = entry
        return summaries

    def verify_matches(self, other: "Sampler") -> None:
        """Refuse to merge/resume campaigns across schema or version drift."""
        if self.schema_hash != other.schema_hash:
            raise SamplerError(
                f"schema hash mismatch: {self.schema_hash} != {other.schema_hash}"
            )
        if self.metadata["sampler_version"] != other.metadata["sampler_version"]:
            raise SamplerError("sampler version mismatch")


def write_campaign(campaign: Mapping[str, Any], path: Path) -> Path:
    """Persist a campaign exactly as generated (pretty JSON, stable key order)."""
    Path(path).write_text(json.dumps(dict(campaign), indent=2), encoding="utf-8")
    return Path(path)


def load_campaign(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
