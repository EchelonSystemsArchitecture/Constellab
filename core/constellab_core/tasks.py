"""Day 27: task lifecycle, observation outcomes and reward data.

Every simulated observable thing becomes a **generic task**: created from an
event target, given a deadline, claimed by a satellite, worked, and closed by an
observation outcome. Nothing in this module branches on the event kind — an
``imaging`` task and a ``change-detection`` task run through the same state
machine and only differ in a registered :class:`TaskHandler` that says how many
observations close the task and how confidence maps to reward.

The state machine is explicit and idempotent:

    available → assigned → in_progress → completed
        ↘ expired ↗        ↘ available (observation rejected) ↗
    any non-terminal → cancelled

Repeating an action that already holds (assigning the same satellite twice,
completing an already completed task) is recorded as a **duplicate**, not an
error; a genuinely illegal action (starting an unassigned task) is rejected with
a reason, and only raises when ``strict=True`` asks it to.

Outcomes come from simulator state plus the Day 26 sensor model — an
:class:`~constellab_core.sensors.AccessWindow` — never from a policy. A policy
proposes; the board decides whether the look produced a usable observation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

TASK_VERSION = "task-lifecycle-1"


class TaskError(ValueError):
    """An illegal task definition or transition (strict mode)."""


class TaskState(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.EXPIRED, TaskState.CANCELLED}
)

# Action -> {source state -> destination state}. One table, no nested branching.
TRANSITIONS: dict[str, dict[TaskState, TaskState]] = {
    "assign": {TaskState.AVAILABLE: TaskState.ASSIGNED},
    "release": {TaskState.ASSIGNED: TaskState.AVAILABLE},
    "start": {TaskState.ASSIGNED: TaskState.IN_PROGRESS},
    "complete": {TaskState.IN_PROGRESS: TaskState.COMPLETED},
    "reject": {TaskState.IN_PROGRESS: TaskState.AVAILABLE},
    "cancel": {
        TaskState.AVAILABLE: TaskState.CANCELLED,
        TaskState.ASSIGNED: TaskState.CANCELLED,
        TaskState.IN_PROGRESS: TaskState.CANCELLED,
    },
    "expire": {
        TaskState.AVAILABLE: TaskState.EXPIRED,
        TaskState.ASSIGNED: TaskState.EXPIRED,
        TaskState.IN_PROGRESS: TaskState.EXPIRED,
    },
}


@dataclass(frozen=True)
class ObservationCostProfile:
    """Resource cost of one acquisition, used to price an outcome."""

    power_w: float = 12.0
    data_rate_bps: float = 2.0e6
    energy_weight: float = 0.15

    def __post_init__(self) -> None:
        if self.power_w < 0.0 or self.data_rate_bps < 0.0:
            raise TaskError("observation cost profile values must be non-negative")
        if not 0.0 <= self.energy_weight <= 1.0:
            raise TaskError("energy_weight must be within [0, 1]")


@runtime_checkable
class TaskHandler(Protocol):
    """Type-specific policy for how many looks close a task and what they earn."""

    key: str
    label: str
    required_observations: int
    revisit_s: float

    def confidence(self, window: Any, target: Any) -> float:
        """Confidence a single access window yields for this task type."""

    def reward(self, task: "Task", confidence: float, freshness: float, cost: float) -> float:
        """Scalar reward for a closed task."""


@dataclass(frozen=True)
class ImagingTask:
    """One good look closes the task; confidence is the window's peak quality."""

    key: str = "task.imaging"
    label: str = "Single-look imaging"
    required_observations: int = 1
    revisit_s: float = 0.0

    def confidence(self, window: Any, target: Any) -> float:
        return float(window.peak_quality)

    def reward(self, task: "Task", confidence: float, freshness: float, cost: float) -> float:
        return round(task.urgency * confidence * freshness - cost, 6)


@dataclass(frozen=True)
class ChangeDetectionTask:
    """Needs a repeat look separated by ``revisit_s``; confidence is the weaker look."""

    key: str = "task.change-detection"
    label: str = "Repeat change detection"
    required_observations: int = 2
    revisit_s: float = 120.0

    def confidence(self, window: Any, target: Any) -> float:
        return float(window.peak_quality)

    def reward(self, task: "Task", confidence: float, freshness: float, cost: float) -> float:
        # A confirmed change is worth more than a single frame of the same target.
        return round(1.25 * task.urgency * confidence * freshness - cost, 6)


_TASK_TYPES: dict[str, TaskHandler] = {}


def register_task_type(handler: TaskHandler) -> TaskHandler:
    key = getattr(handler, "key", None)
    if not isinstance(key, str) or not key:
        raise TaskError("a task handler must declare a non-empty string key")
    if key in _TASK_TYPES:
        raise TaskError(f"task type {key!r} is already registered")
    if handler.required_observations < 1:
        raise TaskError(f"task type {key!r} must require at least one observation")
    _TASK_TYPES[key] = handler
    return handler


def unregister_task_type(key: str) -> TaskHandler | None:
    return _TASK_TYPES.pop(key, None)


def task_type(key: str) -> TaskHandler:
    try:
        return _TASK_TYPES[key]
    except KeyError:
        raise TaskError(
            f"unknown task type {key!r}; registered types: {', '.join(sorted(_TASK_TYPES)) or '(none)'}"
        ) from None


def registered_task_types() -> tuple[str, ...]:
    return tuple(sorted(_TASK_TYPES))


def task_types_payload() -> dict[str, Any]:
    return {
        "version": TASK_VERSION,
        "states": [state.value for state in TaskState],
        "transitions": {
            action: {src.value: dst.value for src, dst in table.items()}
            for action, table in TRANSITIONS.items()
        },
        "types": [
            {
                "key": handler.key,
                "label": handler.label,
                "required_observations": handler.required_observations,
                "revisit_s": handler.revisit_s,
            }
            for _, handler in sorted(_TASK_TYPES.items())
        ],
    }


for _handler in (ImagingTask(), ChangeDetectionTask()):
    register_task_type(_handler)


# Registry role: a task type is selected by target kind through this table, so a
# new event kind can reuse an existing lifecycle instead of editing the board.
DEFAULT_TYPE_FOR_KIND: dict[str, str] = {
    "hotspot": "task.imaging",
    "flood-region": "task.imaging",
    "change-detection": "task.change-detection",
}


@dataclass
class ObservationOutcome:
    """What one simulated look actually produced (simulator-side, not policy)."""

    task_id: str
    satellite_id: str
    target_id: str
    time_s: float
    confidence: float
    freshness: float
    accepted: bool
    resolution_m: float
    duration_s: float
    energy_j: float
    data_bit: float
    reasons: list[str] = field(default_factory=list)

    @property
    def cost(self) -> float:
        """Normalised acquisition cost in ``[0, 1]`` for the reward expression."""
        return round(min(1.0, self.energy_j / 100_000.0 + self.data_bit / 1.0e9), 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "time_s": self.time_s,
            "confidence": round(self.confidence, 6),
            "freshness": round(self.freshness, 6),
            "accepted": self.accepted,
            "resolution_m": round(self.resolution_m, 6),
            "duration_s": round(self.duration_s, 6),
            "energy_j": round(self.energy_j, 6),
            "data_bit": round(self.data_bit, 6),
            "cost": self.cost,
            "reasons": list(self.reasons),
        }


@dataclass
class Transition:
    """One recorded action on one task; rejected and duplicate actions included."""

    task_id: str
    action: str
    at_s: float
    from_state: TaskState
    to_state: TaskState
    accepted: bool = True
    duplicate: bool = False
    reason: str = ""
    satellite_id: str | None = None
    reward: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "at_s": round(self.at_s, 6),
            "from": self.from_state.value,
            "to": self.to_state.value,
            "accepted": self.accepted,
            "duplicate": self.duplicate,
            "reason": self.reason,
            "satellite_id": self.satellite_id,
            "reward": self.reward,
        }


@dataclass
class Task:
    """One generic task, created from an event target."""

    id: str
    type: str
    target_id: str
    created_s: float
    deadline_s: float
    urgency: int = 3
    target: Any = field(default=None, repr=False)
    state: TaskState = TaskState.AVAILABLE
    assigned_to: str | None = None
    attempts: int = 0
    confidence: float = 0.0
    reward: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            raise TaskError("task id must be non-empty")
        task_type(self.type)
        if self.deadline_s <= self.created_s:
            raise TaskError(
                f"task {self.id}: deadline_s ({self.deadline_s}) must exceed created_s ({self.created_s})"
            )
        if not isinstance(self.urgency, int) or isinstance(self.urgency, bool) or not 1 <= self.urgency <= 5:
            raise TaskError(f"task {self.id}: urgency must be an integer in [1, 5]")

    @property
    def handler(self) -> TaskHandler:
        return task_type(self.type)

    @property
    def open(self) -> bool:
        return self.state not in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "target_id": self.target_id,
            "created_s": self.created_s,
            "deadline_s": self.deadline_s,
            "urgency": self.urgency,
            "state": self.state.value,
            "assigned_to": self.assigned_to,
            "attempts": self.attempts,
            "confidence": round(self.confidence, 6),
            "reward": round(self.reward, 6),
        }


def build_tasks(targets: Sequence[Any], *, type_by_kind: Mapping[str, str] | None = None) -> list[Task]:
    """One task per target, in stable id order; deadlines are the event end."""
    mapping = {**DEFAULT_TYPE_FOR_KIND, **dict(type_by_kind or {})}
    tasks: list[Task] = []
    for target in sorted(targets, key=lambda t: t.id):
        type_key = mapping.get(target.kind)
        if type_key is None:
            raise TaskError(
                f"no task type is registered for event kind {target.kind!r}; "
                f"known kinds: {', '.join(sorted(mapping))}"
            )
        tasks.append(
            Task(
                id=f"task.{target.id}",
                type=type_key,
                target_id=target.id,
                created_s=target.start_s,
                deadline_s=target.end_s,
                urgency=target.urgency,
                target=target,
            )
        )
    return tasks


class TaskBoard:
    """Holds tasks and records every transition attempt in order."""

    def __init__(
        self,
        tasks: Sequence[Task],
        *,
        cost_profile: ObservationCostProfile | None = None,
        strict: bool = False,
    ) -> None:
        self._tasks: dict[str, Task] = {}
        for task in tasks:
            if task.id in self._tasks:
                raise TaskError(f"duplicate task id {task.id!r}")
            self._tasks[task.id] = task
        self.cost_profile = cost_profile or ObservationCostProfile()
        self.strict = strict
        self.transitions: list[Transition] = []
        self.outcomes: list[ObservationOutcome] = []
        self._observations: dict[str, list[ObservationOutcome]] = {}

    # --- queries ---------------------------------------------------------------
    def tasks(self) -> list[Task]:
        return [self._tasks[key] for key in sorted(self._tasks)]

    def get(self, task_id: str) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise TaskError(f"unknown task {task_id!r}") from None

    def open_tasks(self, *, time_s: float | None = None) -> list[Task]:
        return [
            task for task in self.tasks()
            if task.open and (time_s is None or task.deadline_s >= time_s)
        ]

    def observations(self, task_id: str) -> list[ObservationOutcome]:
        return list(self._observations.get(task_id, []))

    def metrics(self) -> dict[str, Any]:
        tasks = self.tasks()
        completed = [t for t in tasks if t.state is TaskState.COMPLETED]
        return {
            "tasks": len(tasks),
            "completed": len(completed),
            "expired": sum(1 for t in tasks if t.state is TaskState.EXPIRED),
            "cancelled": sum(1 for t in tasks if t.state is TaskState.CANCELLED),
            "open": sum(1 for t in tasks if t.open),
            "attempts": sum(t.attempts for t in tasks),
            "reward": round(sum(t.reward for t in completed), 6),
            "rejected_actions": sum(1 for tr in self.transitions if not tr.accepted),
            "duplicate_actions": sum(1 for tr in self.transitions if tr.duplicate),
        }

    # --- transitions -----------------------------------------------------------
    def _record(self, transition: Transition) -> Transition:
        self.transitions.append(transition)
        if self.strict and not transition.accepted and not transition.duplicate:
            raise TaskError(
                f"task {transition.task_id}: {transition.action} rejected "
                f"({transition.reason})"
            )
        return transition

    def _reject(self, task: Task, action: str, at_s: float, reason: str,
                satellite_id: str | None = None) -> Transition:
        return self._record(
            Transition(
                task_id=task.id,
                action=action,
                at_s=at_s,
                from_state=task.state,
                to_state=task.state,
                accepted=False,
                reason=reason,
                satellite_id=satellite_id,
            )
        )

    def apply(
        self,
        task_id: str,
        action: str,
        *,
        at_s: float,
        satellite_id: str | None = None,
    ) -> Transition:
        """Apply one lifecycle action; illegal actions are rejected, not raised."""
        task = self.get(task_id)
        table = TRANSITIONS.get(action)
        if table is None:
            return self._reject(task, action, at_s, f"unknown action {action!r}")

        expected = table.get(task.state)
        if expected is None:
            # Idempotent repeat: asking for a state the task already holds.
            if action == "assign" and task.state is TaskState.ASSIGNED:
                if satellite_id is not None and satellite_id != task.assigned_to:
                    return self._reject(
                        task, action, at_s,
                        f"already assigned to {task.assigned_to!r}",
                        satellite_id=satellite_id,
                    )
                return self._record(Transition(
                    task_id=task.id, action=action, at_s=at_s,
                    from_state=task.state, to_state=task.state,
                    duplicate=True, reason="already assigned to this satellite",
                    satellite_id=task.assigned_to,
                ))
            if action == "complete" and task.state is TaskState.COMPLETED:
                return self._record(Transition(
                    task_id=task.id, action=action, at_s=at_s,
                    from_state=task.state, to_state=task.state,
                    duplicate=True, reason="task already completed",
                    satellite_id=task.assigned_to,
                ))
            if action == "cancel" and task.state is TaskState.CANCELLED:
                return self._record(Transition(
                    task_id=task.id, action=action, at_s=at_s,
                    from_state=task.state, to_state=task.state,
                    duplicate=True, reason="task already cancelled",
                ))
            return self._reject(
                task, action, at_s,
                f"cannot {action} a task in state {task.state.value!r}",
                satellite_id=satellite_id,
            )

        if task.state in TERMINAL_STATES:
            return self._reject(task, action, at_s, f"task is {task.state.value!r}")

        if at_s > task.deadline_s and action not in ("expire", "cancel"):
            return self._reject(task, action, at_s, "deadline passed")

        if action == "assign":
            if not satellite_id:
                return self._reject(task, action, at_s, "assign requires a satellite id")
            if at_s < task.created_s:
                return self._reject(task, action, at_s, "task is not visible yet")
            task.assigned_to = satellite_id
        elif action == "release":
            task.assigned_to = None
        elif action == "start":
            if at_s < task.created_s:
                return self._reject(task, action, at_s, "task is not visible yet")
        elif action == "reject":
            task.attempts += 1
            task.assigned_to = None
        elif action == "complete":
            if task.assigned_to is None:
                return self._reject(task, action, at_s, "no observing satellite recorded")

        previous = task.state
        task.state = expected
        return self._record(Transition(
            task_id=task.id, action=action, at_s=at_s,
            from_state=previous, to_state=task.state,
            satellite_id=task.assigned_to,
            reason="",
        ))

    def advance(self, time_s: float) -> list[Transition]:
        """Expire every open task whose deadline has passed, in id order."""
        expired: list[Transition] = []
        for task in self.tasks():
            if task.open and time_s > task.deadline_s:
                expired.append(self.apply(task.id, "expire", at_s=time_s))
        return expired

    # --- observation handling ---------------------------------------------------
    def record_observation(
        self,
        task_id: str,
        window: Any,
        *,
        satellite_id: str,
        time_s: float,
        target: Any | None = None,
    ) -> ObservationOutcome:
        """Turn an access window into an outcome and drive the lifecycle.

        The task must be assigned to ``satellite_id``; an unassigned look is an
        outcome with ``accepted=False`` and a reason, never a silent completion.
        """
        task = self.get(task_id)
        handler = task.handler
        resolved_target = target if target is not None else task.target
        if resolved_target is None:
            raise TaskError(f"task {task_id!r} has no target to evaluate against")
        if task.state is TaskState.COMPLETED:
            outcome = self._outcome(task, window, satellite_id, time_s, resolved_target, handler)
            outcome.accepted = False
            outcome.reasons.append("task already completed")
            self.outcomes.append(outcome)
            return outcome
        if task.state is not TaskState.IN_PROGRESS:
            outcome = self._outcome(task, window, satellite_id, time_s, resolved_target, handler)
            outcome.accepted = False
            outcome.reasons.append(f"task is {task.state.value!r}, not 'in-progress'")
            self.outcomes.append(outcome)
            return outcome
        if task.assigned_to != satellite_id:
            outcome = self._outcome(task, window, satellite_id, time_s, resolved_target, handler)
            outcome.accepted = False
            outcome.reasons.append(f"task is assigned to {task.assigned_to!r}")
            self.outcomes.append(outcome)
            return outcome
        if time_s > task.deadline_s:
            outcome = self._outcome(task, window, satellite_id, time_s, resolved_target, handler)
            outcome.accepted = False
            outcome.reasons.append("deadline passed")
            self.outcomes.append(outcome)
            return outcome

        outcome = self._outcome(task, window, satellite_id, time_s, resolved_target, handler)
        self.outcomes.append(outcome)
        self._observations.setdefault(task.id, []).append(outcome)

        if not outcome.accepted:
            # ``reject`` owns the attempt counter for failed looks.
            self.apply(task.id, "reject", at_s=time_s)
            return outcome

        task.attempts += 1

        prior = [item for item in self._observations[task.id] if item.accepted]
        needed = handler.required_observations
        if len(prior) < needed:
            # More looks are required; keep the task claimed and in progress.
            task.confidence = max(task.confidence, outcome.confidence)
            return outcome

        if needed > 1 and handler.revisit_s > 0.0:
            gap = outcome.time_s - prior[-2].time_s
            if gap < handler.revisit_s:
                outcome.accepted = False
                outcome.reasons.append(
                    f"revisit gap {gap:.1f} s shorter than required {handler.revisit_s:.1f} s"
                )
                self._observations[task.id].pop()
                self.apply(task.id, "reject", at_s=time_s)
                return outcome

        confidence = min(item.confidence for item in prior[-needed:])
        freshness = min(item.freshness for item in prior[-needed:])
        cost = sum(item.cost for item in prior[-needed:])
        reward = handler.reward(task, confidence, freshness, cost)
        task.confidence = confidence
        task.reward = reward
        transition = self.apply(task.id, "complete", at_s=time_s)
        transition.reward = reward
        return outcome

    def _outcome(
        self,
        task: Task,
        window: Any,
        satellite_id: str,
        time_s: float,
        target: Any,
        handler: TaskHandler,
    ) -> ObservationOutcome:
        confidence = handler.confidence(window, target)
        duration = float(getattr(window, "duration_s", 0.0))
        start = float(getattr(target, "start_s", 0.0))
        end = float(getattr(target, "end_s", start + 1.0))
        freshness = max(0.0, min(1.0, 1.0 - (time_s - start) / max(end - start, 1e-9)))
        resolution = float(getattr(window, "best_resolution_m", math.inf))
        reasons: list[str] = []
        if not getattr(window, "usable", False):
            reasons.extend(getattr(window, "reasons", []) or ["access window is not usable"])
        requirements = getattr(target, "requirements", {}) or {}
        min_confidence = requirements.get("min_confidence")
        if min_confidence is not None and confidence < float(min_confidence):
            reasons.append(
                f"confidence {confidence:.3f} below requirement {float(min_confidence):.3f}"
            )
        min_resolution = requirements.get("min_resolution_m")
        if min_resolution is not None and resolution > float(min_resolution):
            reasons.append(
                f"resolution {resolution:.1f} m coarser than required {float(min_resolution):.1f} m"
            )
        energy = duration * self.cost_profile.power_w
        data = duration * self.cost_profile.data_rate_bps
        return ObservationOutcome(
            task_id=task.id,
            satellite_id=satellite_id,
            target_id=target.id,
            time_s=round(float(time_s), 6),
            confidence=round(float(confidence), 6),
            freshness=round(freshness, 6),
            accepted=not reasons,
            resolution_m=resolution,
            duration_s=duration,
            energy_j=round(energy, 6),
            data_bit=round(data, 6),
            reasons=reasons,
        )

    # --- reporting ---------------------------------------------------------------
    def payload(self) -> dict[str, Any]:
        return {
            "version": TASK_VERSION,
            "metrics": self.metrics(),
            "tasks": [task.to_dict() for task in self.tasks()],
            "transitions": [transition.to_dict() for transition in self.transitions],
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }
