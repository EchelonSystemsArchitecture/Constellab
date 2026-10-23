"""Day 28: the policy interface and non-neural reference baselines.

A policy is a pure function of what it is *allowed to know*: it receives a
:class:`PolicyObservation` — satellites with their sensor availability, tasks
that already exist, and predicted access windows — and returns a list of
:class:`Proposal` objects. It never receives a target's ground-truth payload, an
event that has not started yet, or a finished observation result, and it cannot
change simulator state: proposals are validated by the episode harness before
anything happens.

Two transparent baselines are shipped:

* ``local-greedy`` — for each free satellite, claim the open task with the best
  score (urgency, time left, predicted observation quality) and act on it.
  Deterministic tie-breaking by task id, then satellite id, never by target id
  special-casing.
* ``fixed-priority`` — a configured kind order (hotspots before floods before
  change detection), then deadline. This is the "obvious" baseline an operator
  would fly without a learned policy.

``oracle-upper-bound`` is a **diagnostic** ranking that is handed the scene's
ground truth. It exists only to bound what a perfect ranking of the same
opportunities could earn on small scenarios; its metadata says ``deployable:
False`` and the harness refuses to run it unless ``allow_oracle=True``.

``run_episode`` is the shared harness: same observation schema, same action
schema, same trace format for every policy, so baseline traces are comparable
and observation leakage is testable rather than assumed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from . import sensors
from .tasks import (
    Task,
    TaskBoard,
    TaskError,
    TaskState,
    Transition,
    build_tasks,
    registered_task_types,
)

POLICY_VERSION = "policy-interface-1"

PROPOSAL_ACTIONS = ("assign", "wait")

MISSING = "<unavailable>"


class PolicyError(ValueError):
    """A policy contract violation: bad metadata, bad proposal, forbidden access."""


# --- metadata and proposals ---------------------------------------------------------

@dataclass(frozen=True)
class PolicyMetadata:
    """Structured record every policy must expose (used by reports and the UI)."""

    key: str
    label: str
    kind: str  # "baseline" | "learned" | "oracle"
    deployable: bool
    version: str = POLICY_VERSION
    assumptions: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("baseline", "learned", "oracle"):
            raise PolicyError(f"policy kind {self.kind!r} must be baseline, learned or oracle")
        if self.kind == "oracle" and self.deployable:
            raise PolicyError("an oracle policy can never be marked deployable")
        if not self.key:
            raise PolicyError("policy key must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "deployable": self.deployable,
            "version": self.version,
            "assumptions": list(self.assumptions),
            "description": self.description,
        }


@dataclass(frozen=True)
class Proposal:
    """A proposed action; the runtime decides whether it is legal."""

    action: str
    task_id: str
    satellite_id: str
    at_s: float
    score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "task_id": self.task_id,
            "satellite_id": self.satellite_id,
            "at_s": self.at_s,
            "score": round(self.score, 6),
            "reason": self.reason,
        }


# --- observation schema --------------------------------------------------------------

@dataclass(frozen=True)
class PolicyObservation:
    """Everything a policy may see at one simulated instant.

    Built from :class:`Scene.observe`; contains only observable target metadata
    (``EventTarget.observable_view``), already-created tasks, current satellite
    sensor availability and *predicted* access windows derived from orbit and
    sensor configuration. No ``truth`` key can appear here: the constructor
    rejects it.
    """

    time_s: float
    horizon_s: float
    satellites: tuple[dict[str, Any], ...]
    targets: tuple[dict[str, Any], ...]
    tasks: tuple[dict[str, Any], ...]
    access: tuple[dict[str, Any], ...]
    note: str = ""

    def __post_init__(self) -> None:
        for target in self.targets:
            if "truth" in target:
                raise PolicyError(
                    f"observation leaked ground truth for target {target.get('id')!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": POLICY_VERSION,
            "time_s": self.time_s,
            "horizon_s": self.horizon_s,
            "satellites": list(self.satellites),
            "targets": list(self.targets),
            "tasks": list(self.tasks),
            "access": list(self.access),
            "note": self.note,
        }

    def canonical(self) -> str:
        """Stable JSON used by leakage and determinism tests."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@runtime_checkable
class Policy(Protocol):
    """Observation in, proposals out; no hidden simulator access."""

    metadata: PolicyMetadata

    def reset(self) -> None:
        """Drop any episode-local state."""

    def act(self, observation: PolicyObservation) -> list[Proposal]:
        """Propose actions for the current observation (never mutate it)."""


# --- scene: shared input data, no policy state ----------------------------------------

@dataclass
class Scene:
    """A small, fully deterministic episode: targets, opportunities and tasks."""

    config: Any
    targets: list[Any]
    horizon_s: float
    step_s: float = 60.0
    seed: int = 0
    windows: list[sensors.AccessWindow] = field(default_factory=list)
    sensors: dict[str, sensors.SensorConfig] = field(default_factory=dict)
    task_templates: list[Task] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        config: Any,
        targets: Sequence[Any],
        *,
        horizon_s: float,
        step_s: float = 60.0,
        seed: int = 0,
        window_step_s: float = 30.0,
        type_by_kind: Mapping[str, str] | None = None,
    ) -> "Scene":
        windows, sensor_configs = sensors.opportunity_windows(
            config, targets, horizon_s=horizon_s, step_s=window_step_s, seed=seed
        )
        return cls(
            config=config,
            targets=list(targets),
            horizon_s=horizon_s,
            step_s=step_s,
            seed=seed,
            windows=windows,
            sensors=sensor_configs,
            task_templates=build_tasks(targets, type_by_kind=type_by_kind),
        )

    def fresh_tasks(self) -> list[Task]:
        """Unclaimed copies of the template tasks (one per episode)."""
        return [
            dataclasses.replace(
                template,
                state=TaskState.AVAILABLE,
                assigned_to=None,
                attempts=0,
                confidence=0.0,
                reward=0.0,
            )
            for template in self.task_templates
        ]

    def usable_windows(
        self,
        *,
        time_s: float,
        lookahead_s: float | None = None,
        satellite_id: str | None = None,
        target_id: str | None = None,
    ) -> list[sensors.AccessWindow]:
        cutoff = self.horizon_s if lookahead_s is None else min(self.horizon_s, time_s + lookahead_s)
        return [
            window
            for window in self.windows
            if window.usable
            and window.end_s >= time_s
            and window.start_s <= cutoff
            and (satellite_id is None or window.satellite_id == satellite_id)
            and (target_id is None or window.target_id == target_id)
        ]

    def observe(
        self,
        time_s: float,
        *,
        board: TaskBoard | None = None,
        lookahead_s: float = 3_600.0,
    ) -> PolicyObservation:
        """The policy-facing observation at ``time_s`` (no truth, no future events)."""
        target_by_id = {target.id: target for target in self.targets}
        visible_targets = [
            target.observable_view(time_s)
            for target in sorted(self.targets, key=lambda t: t.id)
            if target.start_s <= time_s < target.end_s
        ]
        satellites = []
        for satellite in sorted(self.config.satellites, key=lambda s: s.id):
            sensor = self.sensors[satellite.id]
            model = sensors.sensor_model(sensor.model)
            satellites.append({
                "id": satellite.id,
                "sensor": sensor.model,
                "available": model.is_available(sensor, time_s),
            })
        tasks: list[dict[str, Any]] = []
        if board is not None:
            for task in board.tasks():
                if task.created_s > time_s:
                    continue  # an event that has not started is not knowable
                payload = task.to_dict()
                payload.pop("reward", None)
                target = target_by_id.get(task.target_id)
                payload["kind"] = getattr(target, "kind", MISSING)
                tasks.append(payload)
        access = [
            {
                "satellite_id": window.satellite_id,
                "target_id": window.target_id,
                "start_s": window.start_s,
                "end_s": window.end_s,
                "peak_quality": window.peak_quality,
                "best_resolution_m": window.best_resolution_m,
            }
            for window in self.usable_windows(
                time_s=time_s, lookahead_s=lookahead_s,
            )
            if window.target_id in target_by_id
            and target_by_id[window.target_id].start_s <= time_s < target_by_id[window.target_id].end_s
        ]
        return PolicyObservation(
            time_s=round(float(time_s), 6),
            horizon_s=self.horizon_s,
            satellites=tuple(satellites),
            targets=tuple(visible_targets),
            tasks=tuple(tasks),
            access=tuple(access),
            note="observable metadata only; completion is decided simulator-side",
        )


# --- baselines -----------------------------------------------------------------------

def _task_scores(observation: PolicyObservation) -> dict[str, float]:
    """Normalised urgency/time-left score for every open task (shared helper)."""
    scores: dict[str, float] = {}
    for task in observation.tasks:
        if task["state"] not in ("available",):
            continue
        remaining = max(0.0, float(task["deadline_s"]) - observation.time_s)
        window = max(1.0, float(task["deadline_s"]) - float(task["created_s"]))
        time_left = min(1.0, remaining / window)
        scores[task["id"]] = 0.6 * (float(task["urgency"]) / 5.0) + 0.4 * time_left
    return scores


def _best_window_by_task(observation: PolicyObservation) -> dict[tuple[str, str], dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for window in observation.access:
        key = (window["satellite_id"], window["target_id"])
        current = best.get(key)
        if current is None or (window["peak_quality"], -window["start_s"]) > (
            current["peak_quality"], -current["start_s"]
        ):
            best[key] = window
    return best


class LocalGreedyPolicy:
    """Claim the best-scoring open task each free satellite can actually see."""

    metadata = PolicyMetadata(
        key="local-greedy",
        label="Local greedy",
        kind="baseline",
        deployable=True,
        assumptions=(
            "each satellite acts on its own observable state only",
            "scores use urgency, time left and predicted quality, never truth",
            "assignments are exclusive: one task per satellite at a time",
        ),
        description="Greedy score ranking with deterministic tie-breaking by id.",
    )

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._claimed: set[str] = set()

    def act(self, observation: PolicyObservation) -> list[Proposal]:
        scores = _task_scores(observation)
        windows = _best_window_by_task(observation)
        proposals: list[Proposal] = []
        busy_targets: set[str] = {
            task["target_id"] for task in observation.tasks
            if task["state"] in ("assigned", "in-progress")
        }
        for satellite in observation.satellites:
            if not satellite["available"]:
                continue
            candidates = [
                task for task in observation.tasks
                if task["state"] == "available"
                and task["id"] not in self._claimed
                and task["target_id"] not in busy_targets
                and (satellite["id"], task["target_id"]) in windows
            ]
            if not candidates:
                continue
            candidates.sort(
                key=lambda task: (
                    -scores.get(task["id"], 0.0),
                    -windows[(satellite["id"], task["target_id"])]["peak_quality"],
                    task["id"],
                )
            )
            chosen = candidates[0]
            self._claimed.add(chosen["id"])
            busy_targets.add(chosen["target_id"])
            proposals.append(
                Proposal(
                    action="assign",
                    task_id=chosen["id"],
                    satellite_id=satellite["id"],
                    at_s=observation.time_s,
                    score=round(scores.get(chosen["id"], 0.0), 6),
                    reason="highest urgency/quality score with a usable window",
                )
            )
        return proposals


class FixedPriorityPolicy:
    """Strict kind order, then deadline: the operator's checklist baseline."""

    def __init__(self, priority: Sequence[str] = ("hotspot", "flood-region", "change-detection")) -> None:
        if not priority:
            raise PolicyError("fixed-priority needs at least one event kind")
        self.priority = tuple(priority)
        self.reset()

    metadata = PolicyMetadata(
        key="fixed-priority",
        label="Fixed priority",
        kind="baseline",
        deployable=True,
        assumptions=(
            "kind order is configured, not learned",
            "within a kind, the earliest deadline wins",
            "a satellite only claims a task it has a usable window for",
        ),
        description="Configured event-kind ranking with deadline tie-breaks.",
    )

    def reset(self) -> None:
        self._claimed: set[str] = set()

    def _rank(self, task: Mapping[str, Any]) -> tuple[int, float, str]:
        kind = str(task.get("kind", MISSING))
        try:
            order = self.priority.index(kind)
        except ValueError:
            order = len(self.priority)
        return (order, float(task["deadline_s"]), task["id"])

    def act(self, observation: PolicyObservation) -> list[Proposal]:
        windows = _best_window_by_task(observation)
        proposals: list[Proposal] = []
        busy_targets: set[str] = {
            task["target_id"] for task in observation.tasks
            if task["state"] in ("assigned", "in-progress")
        }
        ordered = sorted(
            [task for task in observation.tasks if task["state"] == "available"],
            key=self._rank,
        )
        for satellite in observation.satellites:
            if not satellite["available"]:
                continue
            for task in ordered:
                if task["id"] in self._claimed or task["target_id"] in busy_targets:
                    continue
                if (satellite["id"], task["target_id"]) not in windows:
                    continue
                self._claimed.add(task["id"])
                busy_targets.add(task["target_id"])
                proposals.append(
                    Proposal(
                        action="assign",
                        task_id=task["id"],
                        satellite_id=satellite["id"],
                        at_s=observation.time_s,
                        score=1.0,
                        reason="first open task in configured priority order",
                    )
                )
                break
        return proposals


class OracleUpperBoundPolicy:
    """Diagnostic only: ranks available tasks by a target's true intensity.

    It deliberately reads simulator ground truth that a deployable policy must
    never see. The metadata marks it non-deployable and the harness refuses to
    run it without ``allow_oracle=True``.
    """

    metadata = PolicyMetadata(
        key="oracle-upper-bound",
        label="Oracle upper bound (diagnostic)",
        kind="oracle",
        deployable=False,
        assumptions=(
            "reads target truth payloads; not a deployable policy",
            "only meaningful on small scenarios as an upper bound",
        ),
        description="Ground-truth ranking used only to bound baseline performance.",
    )

    def __init__(self, scene: Scene) -> None:
        self._truth = {
            target.id: float((target.truth or {}).get("intensity_mw", 0.0))
            for target in scene.targets
        }
        self.reset()

    def reset(self) -> None:
        self._claimed: set[str] = set()

    def act(self, observation: PolicyObservation) -> list[Proposal]:
        windows = _best_window_by_task(observation)
        proposals: list[Proposal] = []
        busy_targets: set[str] = {
            task["target_id"] for task in observation.tasks
            if task["state"] in ("assigned", "in-progress")
        }
        ranked = sorted(
            [task for task in observation.tasks if task["state"] == "available"],
            key=lambda task: (-self._truth.get(task["target_id"], 0.0), task["id"]),
        )
        for satellite in observation.satellites:
            if not satellite["available"]:
                continue
            for task in ranked:
                if task["id"] in self._claimed or task["target_id"] in busy_targets:
                    continue
                if (satellite["id"], task["target_id"]) not in windows:
                    continue
                self._claimed.add(task["id"])
                busy_targets.add(task["target_id"])
                proposals.append(
                    Proposal(
                        action="assign",
                        task_id=task["id"],
                        satellite_id=satellite["id"],
                        at_s=observation.time_s,
                        score=self._truth.get(task["target_id"], 0.0),
                        reason="highest ground-truth intensity (diagnostic)",
                    )
                )
                break
        return proposals


def registered_policy_metadata() -> list[dict[str, Any]]:
    """Metadata for the shipped policies (the UI reads this, not instances)."""
    return [
        LocalGreedyPolicy.metadata.to_dict(),
        FixedPriorityPolicy.metadata.to_dict(),
        OracleUpperBoundPolicy.metadata.to_dict(),
    ]


# --- harness -------------------------------------------------------------------------

@dataclass
class Decision:
    time_s: float
    policy: str
    proposals: list[dict[str, Any]]
    executed: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    observations: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": round(self.time_s, 6),
            "policy": self.policy,
            "proposals": list(self.proposals),
            "executed": list(self.executed),
            "rejected": list(self.rejected),
            "observations": list(self.observations),
        }


@dataclass
class EpisodeResult:
    policy: dict[str, Any]
    metrics: dict[str, Any]
    decisions: list[Decision]
    transitions: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": dict(self.policy),
            "metrics": dict(self.metrics),
            "decisions": [decision.to_dict() for decision in self.decisions],
            "transitions": list(self.transitions),
            "outcomes": list(self.outcomes),
        }

    def trace(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _window_for(
    scene: Scene, satellite_id: str, target_id: str, *, time_s: float, step_s: float
) -> sensors.AccessWindow | None:
    # Only the step in which a window actually opens triggers an acquisition;
    # otherwise the same look would be recorded again on every following step.
    due = [
        window for window in scene.usable_windows(
            time_s=time_s, lookahead_s=step_s, satellite_id=satellite_id, target_id=target_id
        )
        if window.start_s >= time_s - 1e-9 and window.start_s < time_s + step_s - 1e-9
    ]
    if not due:
        return None
    return min(due, key=lambda w: (w.start_s, w.end_s))


def run_episode(
    scene: Scene,
    policy: Policy,
    *,
    allow_oracle: bool = False,
    max_steps: int | None = None,
) -> EpisodeResult:
    """Run one deterministic episode with the shared observation/action schema."""
    if policy.metadata.kind == "oracle" and not allow_oracle:
        raise PolicyError(
            "the oracle policy is diagnostic only; pass allow_oracle=True to bound a "
            "small scenario and never present it as deployable"
        )
    if not policy.metadata.deployable and not allow_oracle:
        raise PolicyError(f"policy {policy.metadata.key!r} is not deployable")

    board = TaskBoard(scene.fresh_tasks())
    policy.reset()
    decisions: list[Decision] = []
    step = scene.step_s
    steps = max_steps if max_steps is not None else int(scene.horizon_s // step) + 1

    for index in range(steps):
        time_s = round(index * step, 6)
        board.advance(time_s)
        observation = scene.observe(time_s, board=board)
        proposals = policy.act(observation)
        executed: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        observed: list[dict[str, Any]] = []

        # 1. service assignments whose access window has arrived
        for task in board.tasks():
            if task.state is not TaskState.IN_PROGRESS or task.assigned_to is None:
                continue
            window = _window_for(
                scene, task.assigned_to, task.target_id, time_s=time_s, step_s=step
            )
            if window is None:
                continue
            outcome = board.record_observation(
                task.id, window,
                satellite_id=task.assigned_to,
                time_s=max(time_s, window.start_s),
            )
            observed.append(outcome.to_dict())

        # 2. validate and execute new proposals
        busy = {
            task.assigned_to for task in board.tasks()
            if task.assigned_to and task.state in (TaskState.ASSIGNED, TaskState.IN_PROGRESS)
        }
        for proposal in proposals:
            record = proposal.to_dict()
            try:
                task = board.get(proposal.task_id)
            except TaskError as exc:  # unknown task id from a policy
                rejected.append({**record, "reason": str(exc)})
                continue
            if proposal.action not in PROPOSAL_ACTIONS:
                rejected.append({**record, "reason": f"unknown action {proposal.action!r}"})
                continue
            if proposal.action == "wait":
                executed.append({**record, "result": "waited"})
                continue
            if task.state is not TaskState.AVAILABLE:
                rejected.append({**record, "reason": f"task is {task.state.value!r}"})
                continue
            if proposal.satellite_id in busy:
                rejected.append({**record, "reason": "satellite already has an assignment"})
                continue
            if task.deadline_s < time_s:
                rejected.append({**record, "reason": "deadline passed"})
                continue

            assigned = board.apply(task.id, "assign", at_s=time_s,
                                   satellite_id=proposal.satellite_id)
            if not assigned.accepted:
                rejected.append({**record, "reason": assigned.reason})
                continue
            started = board.apply(task.id, "start", at_s=time_s)
            if not started.accepted:
                rejected.append({**record, "reason": started.reason})
                continue
            busy.add(proposal.satellite_id)
            executed.append({**record, "result": "assigned"})
            window = _window_for(
                scene, proposal.satellite_id, task.target_id, time_s=time_s, step_s=step
            )
            if window is not None:
                outcome = board.record_observation(
                    task.id, window,
                    satellite_id=proposal.satellite_id,
                    time_s=max(time_s, window.start_s),
                )
                observed.append(outcome.to_dict())

        decisions.append(Decision(
            time_s=time_s,
            policy=policy.metadata.key,
            proposals=[proposal.to_dict() for proposal in proposals],
            executed=executed,
            rejected=rejected,
            observations=observed,
        ))

    metrics = board.metrics()
    metrics.update({
        "policy": policy.metadata.key,
        "deployable": policy.metadata.deployable,
        "proposals": sum(len(decision.proposals) for decision in decisions),
        "conflicts": sum(1 for decision in decisions for _ in decision.rejected),
        "usable_windows": sum(1 for window in scene.windows if window.usable),
    })
    return EpisodeResult(
        policy=policy.metadata.to_dict(),
        metrics=metrics,
        decisions=decisions,
        transitions=[transition.to_dict() for transition in board.transitions],
        outcomes=[outcome.to_dict() for outcome in board.outcomes],
    )


def compare_baselines(scene: Scene, *, allow_oracle: bool = False) -> dict[str, Any]:
    """Run each shipped baseline through the same harness and compare traces."""
    results: dict[str, Any] = {}
    policies: list[Policy] = [LocalGreedyPolicy(), FixedPriorityPolicy()]
    if allow_oracle:
        policies.append(OracleUpperBoundPolicy(scene))
    for policy in policies:
        result = run_episode(scene, policy, allow_oracle=allow_oracle and policy.metadata.kind == "oracle")
        results[policy.metadata.key] = {
            "policy": result.policy,
            "metrics": result.metrics,
            "trace_hash": hashlib.sha256(result.trace().encode("utf-8")).hexdigest()[:16],
        }
    return {
        "version": POLICY_VERSION,
        "task_types": list(registered_task_types()),
        "episode": {"horizon_s": scene.horizon_s, "step_s": scene.step_s, "seed": scene.seed},
        "policies": results,
    }
