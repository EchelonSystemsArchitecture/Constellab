"""Day 20: the plugin/component registry — discover, validate, activate, shutdown.

Day 18's component models and Day 15's dynamics models are implementations; Day
20 is the *lifecycle* around them. A :class:`Plugin` declares a stable id, a
semantic version, what it registers, the host version it needs, and an
activation hook that performs its registrations. Activation is a single ordered
pass that runs before any scenario is accepted, and :meth:`PluginHost.report`
produces the startup diagnostic the service and CLI expose: anything that used
to fail silently at runtime instead fails loudly at startup (duplicate plugin
ids, incompatible host versions, duplicate registration keys).

Everything a plugin registers is trusted code shipped with, or vetted by,
ConstellaLab. Client configuration stays data-only: a scenario selects
registered component keys and parameter values and can never execute plugin
code. That separation lets a third-party-style plugin participate without any
edit to the simulation core, the validator or the renderer — the acceptance
evidence for this day.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .components import (
    BufferStorage,
    ClockTickSource,
    ComponentError,
    ComputeCapacity,
    ConicalSensor,
    ConstantSupply,
    ImagingPayload,
    RoundRobinTasks,
    SolarBattery,
    registered_components,
    register_component,
)

PLUGIN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")

# Plugins are built against the core version and declare the minimum they need.
HOST_VERSION = "0.3.0"


class PluginError(ValueError):
    """A plugin registration or activation is invalid (startup diagnostic)."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("plugin error: " + "; ".join(f"{i['path']}: {i['message']}" for i in issues))


def parse_version(version: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", str(version or ""))
    if not match:
        raise ValueError(f"not a semantic version: {version!r}")
    return int(match[1]), int(match[2]), int(match[3])


def version_satisfied(required: str, actual: str) -> bool:
    """True when ``actual`` is at least ``required`` (per-field semantics)."""
    return parse_version(actual) >= parse_version(required)


@dataclass(frozen=True)
class Plugin:
    """One lifecycle unit: declare, then activate and optionally tear down.

    ``activate`` is explicitly allowed to be trusted executable code: it
    performs registrations (component models, dynamics models) exactly once.
    ``teardown`` is the mirror image used by tests and future hot-reload paths;
    it must be idempotent and must not raise.
    """

    id: str
    version: str
    label: str
    provides: tuple[str, ...]
    min_host_version: str = HOST_VERSION
    builtin: bool = False
    priority: int = 0
    activate: Callable[[], None] | None = None
    teardown: Callable[[], None] | None = None


@dataclass
class PluginEntry:
    plugin: Plugin
    issues: list[dict[str, str]] = field(default_factory=list)
    status: str = "registered"  # registered -> active | failed
    provides: list[str] = field(default_factory=list)


class PluginHost:
    """Ordered plugin lifecycle with actionable startup diagnostics."""

    def __init__(self) -> None:
        self._entries: dict[str, PluginEntry] = {}
        self.activated: bool = False

    def register_plugin(self, plugin: Plugin) -> PluginEntry:
        """Declare a plugin; anything invalid fails here with a diagnostic."""
        issues: list[dict[str, str]] = []
        path = f"plugin[{plugin.id!r}]"
        if not isinstance(plugin.id, str) or not PLUGIN_KEY_PATTERN.match(plugin.id or ""):
            issues.append({
                "path": f"{path}.id",
                "message": "plugin id must be lower-case namespaced like 'constellab.builtin-power'",
            })
            path = f"plugin[{plugin.id!r}]"
        elif plugin.id in self._entries:
            issues.append({
                "path": f"{path}.id",
                "message": f"plugin id is already registered ({self._entries[plugin.id].plugin.label}); "
                           f"plugin ids must be unique",
            })
        try:
            parse_version(plugin.version)
        except ValueError as exc:
            issues.append({"path": f"{path}.version", "message": str(exc)})
        try:
            version_satisfied(plugin.min_host_version, HOST_VERSION)
        except ValueError as exc:
            issues.append({"path": f"{path}.min_host_version", "message": str(exc)})
        else:
            if not version_satisfied(plugin.min_host_version, HOST_VERSION):
                issues.append({
                    "path": f"{path}.min_host_version",
                    "message": f"incompatible plugin: needs host >= {plugin.min_host_version}, "
                               f"running host is {HOST_VERSION}",
                })
        if not plugin.provides:
            issues.append({"path": f"{path}.provides",
                           "message": "a plugin must provide at least one registration key"})
        else:
            if len(set(plugin.provides)) != len(plugin.provides):
                issues.append({"path": f"{path}.provides",
                               "message": "provides contains duplicate keys"})
            for key in plugin.provides:
                if not isinstance(key, str):
                    issues.append({"path": f"{path}.provides",
                                   "message": "provides entries must be keys (strings)"})
                    break
            else:
                duplicates = [key for key in plugin.provides if key in registered_components()]
                if duplicates:
                    issues.append({
                        "path": f"{path}.provides",
                        "message": f"registration keys already registered: {', '.join(duplicates)}",
                    })
        entry = PluginEntry(plugin=plugin, issues=issues)
        if not issues:
            self._entries[plugin.id] = entry
            path = f"plugin[{plugin.id!r}]"
        return entry

    def entries(self) -> list[PluginEntry]:
        return [self._entries[key] for key in sorted(self._entries)]

    def activate_all(self) -> list[dict[str, Any]]:
        """Activate registered plugins in (priority, id) order; return the report."""
        self.activated = False
        for entry in self._entries.values():
            if entry.status == "active":
                entry.status = "registered"
        report: list[dict[str, Any]] = []
        for entry in sorted(self._entries.values(), key=lambda e: (e.plugin.priority, e.plugin.id)):
            if entry.status == "failed":
                continue
            try:
                if entry.plugin.activate is not None:
                    entry.plugin.activate()
                entry.status = "active"
                entry.provides = list(entry.plugin.provides)
            except Exception as exc:  # noqa: BLE001 - startup diagnostics must name the cause
                entry.status = "failed"
                entry.issues.append({"path": f"plugin[{entry.plugin.id!r}].activate",
                                     "message": f"activation failed: {exc}"})
            report.append({
                "id": entry.plugin.id,
                "version": entry.plugin.version,
                "label": entry.plugin.label,
                "builtin": entry.plugin.builtin,
                "priority": entry.plugin.priority,
                "status": entry.status,
                "provides": list(entry.provides),
                "issues": list(entry.issues),
            })
        self.activated = True
        return report

    def shutdown_all(self) -> None:
        """Best-effort teardown in reverse activation order."""
        for entry in sorted(self._entries.values(),
                            key=lambda e: (e.plugin.priority, e.plugin.id), reverse=True):
            if entry.status == "active" and entry.plugin.teardown is not None:
                try:
                    entry.plugin.teardown()
                except Exception:  # noqa: BLE001 - teardown must never mask the stop path
                    pass
            if entry.status == "active":
                entry.status = "registered"

    def _entry(self, plugin: Plugin) -> PluginEntry | None:
        return self._entries.get(plugin.id)

    def report(self) -> dict[str, Any]:
        """Complete machine-readable startup diagnostic (idempotent)."""
        plugins = [{
            "id": entry.plugin.id,
            "version": entry.plugin.version,
            "label": entry.plugin.label,
            "builtin": entry.plugin.builtin,
            "priority": entry.plugin.priority,
            "status": entry.status,
            "provides": list(entry.plugin.provides),
            "issues": list(entry.issues),
        } for entry in self.entries()]
        return {
            "host_version": HOST_VERSION,
            "status": "degraded" if any(p["status"] == "failed" for p in plugins) else "ok",
            "count": len(plugins),
            "builtin": sum(1 for p in plugins if p["builtin"]),
            "plugins": plugins,
        }


_PEER_REGISTERED: tuple[str, ...] = ()


def _activate_builtin_components(providers: tuple[type, ...]) -> None:
    """Register a family of built-in models, tolerating idempotent re-activation."""
    for factory in providers:
        model = factory()
        try:
            register_component(model)
        except ComponentError:
            if model.key not in registered_components():
                raise


# --- the built-in plugin set ---------------------------------------------------------

def builtin_plugins() -> tuple[Plugin, ...]:
    """The plugin set shipped with the core, one per component family."""
    return (
        Plugin(
            id="constellab.builtin-power", version="1.0.0",
            label="Reference power components",
            provides=("power.solar-battery", "power.constant"),
            builtin=True, priority=10,
            activate=lambda: _activate_builtin_components((SolarBattery, ConstantSupply)),
        ),
        Plugin(
            id="constellab.builtin-sensors", version="1.0.0",
            label="Reference sensor component",
            provides=("sensor.conical",),
            builtin=True, priority=20,
            activate=lambda: _activate_builtin_components((ConicalSensor,)),
        ),
        Plugin(
            id="constellab.builtin-payloads", version="1.0.0",
            label="Reference payload component",
            provides=("payload.imaging",),
            builtin=True, priority=30,
            activate=lambda: _activate_builtin_components((ImagingPayload,)),
        ),
        Plugin(
            id="constellab.builtin-storage", version="1.0.0",
            label="Reference storage component",
            provides=("storage.buffer",),
            builtin=True, priority=40,
            activate=lambda: _activate_builtin_components((BufferStorage,)),
        ),
        Plugin(
            id="constellab.builtin-compute", version="1.0.0",
            label="Reference compute component",
            provides=("compute.capacity",),
            builtin=True, priority=50,
            activate=lambda: _activate_builtin_components((ComputeCapacity,)),
        ),
        Plugin(
            id="constellab.builtin-tasks", version="1.0.0",
            label="Reference task component",
            provides=("task.round-robin",),
            builtin=True, priority=60,
            activate=lambda: _activate_builtin_components((RoundRobinTasks,)),
        ),
        Plugin(
            id="constellab.builtin-event-sources", version="1.0.0",
            label="Reference event-source component",
            provides=("event-source.clock-tick",),
            builtin=True, priority=70,
            activate=lambda: _activate_builtin_components((ClockTickSource,)),
        ),
    )


_HOST: PluginHost | None = None


def host() -> PluginHost:
    global _HOST
    if _HOST is None:
        _HOST = PluginHost()
    return _HOST


def activate_builtins() -> dict[str, Any]:
    """Register and activate the built-in plugin set (idempotent)."""
    plugins = builtin_plugins()
    if not host().activated:
        for plugin in plugins:
            host().register_plugin(plugin)
        host().activate_all()
    return host().report()


def fresh_host() -> PluginHost:
    """A private PluginHost for tests and diagnostics, without touching the global."""
    return PluginHost()
