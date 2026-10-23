"""Day 27 acceptance tests: task lifecycle, outcomes and reward data."""

import json
import unittest

from constellab_core import tasks as task_registry
from constellab_core.sensors import AccessWindow
from constellab_core.targets import EventTarget
from constellab_core.tasks import (
    Task,
    TaskBoard,
    TaskError,
    TaskState,
    build_tasks,
    register_task_type,
    registered_task_types,
    task_type,
    task_types_payload,
    unregister_task_type,
)


def make_target(**overrides) -> EventTarget:
    payload = {
        "id": "hotspot.fire-01",
        "kind": "hotspot",
        "lat_deg": 12.0,
        "lon_deg": 34.0,
        "start_s": 0.0,
        "end_s": 1_200.0,
        "urgency": 4,
        "requirements": {},
    }
    payload.update(overrides)
    return EventTarget(**payload)


def make_window(*, quality: float = 0.8, usable: bool = True, duration_s: float = 40.0,
                resolution_m: float = 8.0, reasons: list[str] | None = None) -> AccessWindow:
    return AccessWindow(
        satellite_id="sat-alpha",
        target_id="hotspot.fire-01",
        model="sensor.conical",
        start_s=100.0,
        end_s=100.0 + duration_s,
        peak_quality=quality,
        mean_quality=quality * 0.9,
        best_resolution_m=resolution_m,
        usable=usable,
        reasons=list(reasons or []),
    )


def make_task(**overrides) -> Task:
    target = overrides.pop("target", None) or make_target()
    payload = {
        "id": "task.hotspot.fire-01",
        "type": "task.imaging",
        "target_id": target.id,
        "created_s": target.start_s,
        "deadline_s": target.end_s,
        "urgency": target.urgency,
        "target": target,
    }
    payload.update(overrides)
    return Task(**payload)


class TaskTypeRegistryTests(unittest.TestCase):
    def test_two_types_share_the_core_lifecycle(self) -> None:
        self.assertIn("task.imaging", registered_task_types())
        self.assertIn("task.change-detection", registered_task_types())
        payload = task_types_payload()
        self.assertEqual(
            payload["states"],
            ["available", "assigned", "in-progress", "completed", "expired", "cancelled"],
        )
        self.assertEqual(payload["transitions"]["assign"], {"available": "assigned"})

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(TaskError) as caught:
            task_type("task.teleport")
        self.assertIn("task.imaging", str(caught.exception))

    def test_duplicate_registration_fails(self) -> None:
        with self.assertRaises(TaskError):
            register_task_type(task_registry.ImagingTask())

    def test_a_new_type_joins_without_board_edits(self) -> None:
        # A third-party handler is just another object satisfying the interface.
        handler = task_registry.ImagingTask(key="task.long-look", label="Long look")
        register_task_type(handler)
        try:
            board = TaskBoard([make_task(type="task.long-look")])
            board.apply("task.hotspot.fire-01", "assign", at_s=0.0, satellite_id="sat-alpha")
            board.apply("task.hotspot.fire-01", "start", at_s=5.0)
            board.record_observation(
                "task.hotspot.fire-01", make_window(), satellite_id="sat-alpha", time_s=100.0
            )
            self.assertIs(board.get("task.hotspot.fire-01").state, TaskState.COMPLETED)
        finally:
            unregister_task_type("task.long-look")


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = make_task()
        self.board = TaskBoard([self.task])
        self.task_id = self.task.id

    def test_legal_path_completes_task(self) -> None:
        assigned = self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        self.assertTrue(assigned.accepted)
        self.assertIs(assigned.to_state, TaskState.ASSIGNED)
        started = self.board.apply(self.task_id, "start", at_s=20.0)
        self.assertIs(started.to_state, TaskState.IN_PROGRESS)
        outcome = self.board.record_observation(
            self.task_id, make_window(), satellite_id="sat-alpha", time_s=100.0
        )
        self.assertTrue(outcome.accepted)
        task = self.board.get(self.task_id)
        self.assertIs(task.state, TaskState.COMPLETED)
        self.assertGreater(task.reward, 0.0)
        self.assertEqual(self.board.metrics()["completed"], 1)

    def test_illegal_transitions_are_rejected_with_reasons(self) -> None:
        started = self.board.apply(self.task_id, "start", at_s=10.0)
        self.assertFalse(started.accepted)
        self.assertIn("cannot start", started.reason)
        completed = self.board.apply(self.task_id, "complete", at_s=10.0)
        self.assertFalse(completed.accepted)
        self.assertIs(self.board.get(self.task_id).state, TaskState.AVAILABLE)
        self.assertEqual(self.board.metrics()["rejected_actions"], 2)

    def test_strict_mode_raises_on_illegal_transition(self) -> None:
        board = TaskBoard([make_task()], strict=True)
        with self.assertRaises(TaskError):
            board.apply("task.hotspot.fire-01", "start", at_s=1.0)

    def test_repeated_assign_is_a_duplicate_not_an_error(self) -> None:
        self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        again = self.board.apply(self.task_id, "assign", at_s=11.0, satellite_id="sat-alpha")
        self.assertTrue(again.accepted)
        self.assertTrue(again.duplicate)
        other = self.board.apply(self.task_id, "assign", at_s=12.0, satellite_id="sat-beta")
        self.assertFalse(other.accepted)
        self.assertIn("already assigned", other.reason)

    def test_repeated_complete_is_idempotent(self) -> None:
        self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        self.board.apply(self.task_id, "start", at_s=20.0)
        self.board.record_observation(
            self.task_id, make_window(), satellite_id="sat-alpha", time_s=100.0
        )
        again = self.board.apply(self.task_id, "complete", at_s=110.0)
        self.assertTrue(again.duplicate)
        self.assertIs(self.board.get(self.task_id).state, TaskState.COMPLETED)

    def test_deadline_blocks_assignment_and_expires_open_tasks(self) -> None:
        late = self.board.apply(self.task_id, "assign", at_s=1_300.0, satellite_id="sat-alpha")
        self.assertFalse(late.accepted)
        self.assertIn("deadline passed", late.reason)
        self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        expired = self.board.advance(1_201.0)
        self.assertEqual(len(expired), 1)
        self.assertIs(self.board.get(self.task_id).state, TaskState.EXPIRED)

    def test_cancel_is_terminal_and_cannot_be_reopened(self) -> None:
        self.board.apply(self.task_id, "cancel", at_s=5.0)
        self.assertIs(self.board.get(self.task_id).state, TaskState.CANCELLED)
        reopened = self.board.apply(self.task_id, "assign", at_s=6.0, satellite_id="sat-alpha")
        self.assertFalse(reopened.accepted)
        self.assertIn("cancelled", reopened.reason)

    def test_release_returns_task_to_available(self) -> None:
        self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        released = self.board.apply(self.task_id, "release", at_s=15.0)
        self.assertIs(released.to_state, TaskState.AVAILABLE)
        self.assertIsNone(self.board.get(self.task_id).assigned_to)


class ObservationOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = TaskBoard([make_task()])
        self.task_id = "task.hotspot.fire-01"
        self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        self.board.apply(self.task_id, "start", at_s=20.0)

    def test_outcome_records_confidence_freshness_and_resource_cost(self) -> None:
        outcome = self.board.record_observation(
            self.task_id, make_window(quality=0.7, duration_s=60.0),
            satellite_id="sat-alpha", time_s=600.0,
        )
        self.assertTrue(outcome.accepted)
        self.assertAlmostEqual(outcome.confidence, 0.7, places=6)
        self.assertGreater(outcome.freshness, 0.0)
        self.assertLess(outcome.freshness, 1.0)
        self.assertGreater(outcome.energy_j, 0.0)
        self.assertGreater(outcome.data_bit, 0.0)
        payload = outcome.to_dict()
        for key in ("confidence", "freshness", "cost", "energy_j", "data_bit"):
            self.assertIn(key, payload)

    def test_unusable_window_rejects_and_returns_task_to_available(self) -> None:
        outcome = self.board.record_observation(
            self.task_id,
            make_window(usable=False, reasons=["sensor unavailable (duty cycle)"]),
            satellite_id="sat-alpha", time_s=100.0,
        )
        self.assertFalse(outcome.accepted)
        self.assertIn("sensor unavailable", " ".join(outcome.reasons))
        task = self.board.get(self.task_id)
        self.assertIs(task.state, TaskState.AVAILABLE)
        self.assertEqual(task.attempts, 1)

    def test_target_requirement_blocks_completion(self) -> None:
        target = make_target(requirements={"min_confidence": 0.95})
        board = TaskBoard([make_task(target=target)])
        board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        board.apply(self.task_id, "start", at_s=20.0)
        outcome = board.record_observation(
            self.task_id, make_window(quality=0.6), satellite_id="sat-alpha", time_s=100.0
        )
        self.assertFalse(outcome.accepted)
        self.assertIn("below requirement", " ".join(outcome.reasons))

    def test_observation_on_another_satellites_task_is_not_accepted(self) -> None:
        outcome = self.board.record_observation(
            self.task_id, make_window(), satellite_id="sat-beta", time_s=100.0
        )
        self.assertFalse(outcome.accepted)
        self.assertIn("assigned to", " ".join(outcome.reasons))
        self.assertIs(self.board.get(self.task_id).state, TaskState.IN_PROGRESS)

    def test_observation_before_progress_is_not_accepted(self) -> None:
        board = TaskBoard([make_task()])
        outcome = board.record_observation(
            self.task_id, make_window(), satellite_id="sat-alpha", time_s=100.0
        )
        self.assertFalse(outcome.accepted)
        self.assertIn("not 'in-progress'", " ".join(outcome.reasons))


class MultiObservationTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        target = make_target(id="change-01", kind="change-detection", requirements={})
        self.board = TaskBoard([make_task(id="task.change-01", type="task.change-detection",
                                         target_id="change-01", target=target)])
        self.task_id = "task.change-01"
        self.board.apply(self.task_id, "assign", at_s=10.0, satellite_id="sat-alpha")
        self.board.apply(self.task_id, "start", at_s=20.0)

    def test_one_look_is_not_enough_for_change_detection(self) -> None:
        outcome = self.board.record_observation(
            self.task_id, make_window(quality=0.8), satellite_id="sat-alpha", time_s=100.0
        )
        self.assertTrue(outcome.accepted)
        self.assertIs(self.board.get(self.task_id).state, TaskState.IN_PROGRESS)
        self.board.record_observation(
            self.task_id, make_window(quality=0.9), satellite_id="sat-alpha", time_s=400.0
        )
        task = self.board.get(self.task_id)
        self.assertIs(task.state, TaskState.COMPLETED)
        # The weaker of the two looks sets the confidence.
        self.assertAlmostEqual(task.confidence, 0.8, places=6)

    def test_revisit_inside_the_gap_is_rejected(self) -> None:
        self.board.record_observation(
            self.task_id, make_window(quality=0.8), satellite_id="sat-alpha", time_s=100.0
        )
        outcome = self.board.record_observation(
            self.task_id, make_window(quality=0.8), satellite_id="sat-alpha", time_s=150.0
        )
        self.assertFalse(outcome.accepted)
        self.assertIn("revisit gap", " ".join(outcome.reasons))
        self.assertIs(self.board.get(self.task_id).state, TaskState.AVAILABLE)


class TaskBuildTests(unittest.TestCase):
    def test_tasks_follow_targets_and_type_mapping(self) -> None:
        targets = [
            make_target(id="a.fire", kind="hotspot", start_s=10.0, end_s=500.0),
            make_target(id="b.change", kind="change-detection", start_s=0.0, end_s=900.0),
        ]
        built = build_tasks(targets)
        self.assertEqual([t.id for t in built], ["task.a.fire", "task.b.change"])
        self.assertEqual(built[0].type, "task.imaging")
        self.assertEqual(built[1].type, "task.change-detection")
        self.assertEqual(built[0].deadline_s, 500.0)
        self.assertNotIn("truth", json.dumps([t.to_dict() for t in built]))

    def test_missing_type_for_kind_is_an_explicit_error(self) -> None:
        targets = [make_target(id="weird", kind="hotspot")]
        with self.assertRaises(TaskError):
            build_tasks(targets, type_by_kind={"hotspot": "task.unknown"})

    def test_invalid_task_definitions_are_rejected(self) -> None:
        with self.assertRaises(TaskError):
            make_task(deadline_s=0.0)
        with self.assertRaises(TaskError):
            make_task(urgency=9)


if __name__ == "__main__":
    unittest.main()
