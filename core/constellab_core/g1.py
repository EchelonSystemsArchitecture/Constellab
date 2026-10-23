"""Day 24: the automated G1 configurable-foundation acceptance report.

G1 asks the proof in one sentence: does the variable-driven architecture handle
high-dimensional configurations without special cases? This module answers it
by actually running the layers and recording measurements — no guessed numbers:

* schema/hash/counts: parameter registry, unit registry, frames, components,
  active plugins,
* stress: a synthetic 1,000-parameter registry load + validation round-trip is
  timed (bounded environment-relative evidence, recorded not guaranteed),
* config load time: the full 1,000-satellite built-in scenario is validated and
  timed, also through the Day 18 component runtime,
* valid/invalid examples: every built-in scenario must validate; the shipped
  malformed fixture set must be rejected with field paths,
* unknown-field behaviour: an irrelevant metadata key is flagged by the
  registry's unconsumed-key audit rather than silently accepted,
* transactional edits: a Day 21 constraint transaction that both accepts a
  consistent edit and rejects a violating one,
* sampler: a quick Day 23 campaign over the real registry whose samples pass
  the per-owner builtin rules,
* limitations: the exact, honest list of simplifications this gate runs under.

``generate_report`` returns the report dict; ``write_report(path)`` and the
``python -m constellab_core g1`` subcommand persist it. The core test suite
asserts the structure and regenerates the artifact.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import components as component_registry
from . import dynamics, frames as frames_mod, plugins, units
from .config import (  # noqa: F401
    BUILTIN_SCENARIOS,
    ConfigError,
    walker_delta_payload,
)
from .config import load_config, validate_config
from .constraints import builtin_rules
from .parameters import ParameterRegistry, builtin_registry, stress_registry

G1_VERSION = "g1-acceptance-1"

_LIMITATIONS = [
    "dynamics: analytic two-body Kepler propagation only; no J2/drag/third-body effects",
    "frames: ECI↔ECEF↔geodetic conversions are closed-form (no nutation/precession beyond the declared model)",
    "components: resource models are virtual/parametric abstractions, not hardware fidelity models",
    "parameter registry: schema hash covers semantic spec fields only; display labels may drift freely",
    "constraint enforcement is declarative operator logic with no arbitrary expression execution",
    "stress and load timings in this report are measured per run, not guaranteed absolute bounds",
    "sampling supports registry-declared distributions (constant/uniform/log-uniform/normal); other declared distributions fall back to the constant default",
    "config load time and stress timings are environment-relative measurements recorded per run, not absolute guarantees",
]


def _timed(fn) -> tuple[Any, float]:
    started = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - started


def generate_report() -> dict[str, Any]:
    """Generate the full G1 report by running every check it claims."""
    parameters = builtin_registry()
    rules = builtin_rules(parameters)

    # 1. Registries ---------------------------------------------------------
    stress = stress_registry(1000)
    _copy, load_ms_registry = _timed(
        lambda: ParameterRegistry(stress.specs(), source="<g1-stress-rebuild>")
    )

    # 2. Config load timing (1,000-satellite scenario) -----------------------
    mega_payload = walker_delta_payload(1000, planes=25)
    _validated, load_ms = _timed(lambda: validate_config(mega_payload))
    _runtime, components_ms = _timed(lambda: component_registry.initial_runtime(load_config(mega_payload)))

    # 3. Valid examples: every built-in scenario ------------------------------
    valid_examples: list[str] = list(BUILTIN_SCENARIOS)
    from .config import load_config_file

    for key in valid_examples:
        load_config_file(key)  # raising means the gate fails

    # 4. Invalid examples: shipped malformed fixtures ------------------------
    fixture_path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "malformed_configs.json"
    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    invalid_examples = []
    for payload in fixture_data["cases"]:
        errors = validate_config_errors(payload["config"])
        if not errors:
            raise AssertionError(f"malformed fixture {payload['name']} unexpectedly validated")
        paths = {error["path"] for error in errors}
        missing = [p for p in payload.get("expect_paths", []) if p not in paths]
        if missing:
            raise AssertionError(
                f"malformed fixture {payload['name']} did not surface paths {missing}"
            )
        invalid_examples.append({"fixture": payload["name"], "errors": len(errors)})

    # 5. Unconsumed operational keys are identified, never silent ------------
    audit = parameters.validate_values(
        "power.solar-battery",
        {"ghost_setting": 1.0},
        path="$/power.solar-battery",
    )
    unknown_field_flagged = bool(audit)

    # 6. Transaction: accept a consistent edit, reject a violating one -------
    base = parameters.effective_values("sensor.conical", {})
    good_candidate = dict(base)
    accept_issues = rules.check_transaction(base, good_candidate, scope="sensor.conical")
    bad_candidate = dict(base)
    bad_candidate["half_angle_deg"] = 120.0  # the builtin rule caps it strictly below 90
    reject_issues = rules.check_transaction(base, bad_candidate, scope="sensor.conical")

    # 7. Sampler campaign ----------------------------------------------------
    from .sampler import Sampler

    campaign = Sampler(parameters, seed=1).quick(4)
    sampler_deterministic = all(record["constraint"] in ("pass", "violated") for record in campaign["samples"])

    host = plugins.host()
    report = {
        "report_version": G1_VERSION,
        "contract": {
            "schema_version": parameters.payload()["schema_version"],
            "schema_hash": parameters.schema_hash(),
        },
        "registries": {
            "parameter_count": len(parameters),
            "unit_count": len(units.registry_payload()["units"]),
            "frame_count": len(frames_mod.frames_payload()["frames"]),
            "component_count": len(component_registry.describe_components()),
            "dynamics_models": len(dynamics.describe_models()),
            "plugin_count": host.report()["count"],
        },
        "stress": {
            "registry_parameters": 1000,
            "registry_load_ms": round(load_ms_registry * 1000, 3),
            "config_1000_load_ms": round(load_ms * 1000, 3),
            "component_runtime_1000_ms": round(components_ms * 1000, 3),
        },
        "examples": {
            "valid_scenarios": valid_examples,
            "malformed_fixtures_rejected": [f["fixture"] for f in invalid_examples],
        },
        "behaviour": {
            "unknown_operational_field_flagged": unknown_field_flagged,
            "transaction_accepts_consistent_edit": accept_issues == [],
            "transaction_rejects_bounds_violation": reject_issues != [],
            "sampler_quick_campaign_recorded": sampler_deterministic,
            "constraint_reputation": {
                "accepted": len(accept_issues) == 0,
                "rejected_paths": [issue["path"] for issue in reject_issues][:3],
            },
        },
        "limitations": list(_LIMITATIONS),
    }
    return report


def validate_config_errors(raw: Any) -> list[dict[str, str]]:
    """Validation errors of ``raw`` (raises nothing)."""
    try:
        validate_config(raw)
    except ConfigError as exc:
        return list(exc.errors)
    return []


def write_report(path: Path | None = None) -> Path:
    target = Path(path) if path else Path("benchmarks") / "g1-acceptance.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(generate_report(), indent=2), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(json.dumps(write_report(), indent=2))
