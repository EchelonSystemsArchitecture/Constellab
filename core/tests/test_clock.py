"""Day 6 acceptance: pause / resume / reset / step / time-scale semantics.

The clock endpoints are the only way the renderer changes time. These tests pin
the promises the UI and headless runs rely on:

* pause freezes simulated time and leaves the state untouched,
* resume continues from the frozen time,
* reset restores the exact epoch snapshot (positions and clock),
* a single step advances exactly one simulated second and never unpauses,
* time scale changes how fast simulated time runs, not what is rendered,
* an invalid scale is rejected and leaves the current clock alone.
"""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.config import builtin_scenario  # noqa: E402
from constellab_core.orbit import initial_snapshot, snapshot_at_time  # noqa: E402
from constellab_core.service import CoreHandler, serve  # noqa: E402


class TestClockControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._log = CoreHandler.log_message
        CoreHandler.log_message = lambda *a, **k: None
        cls.server = serve("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        CoreHandler.log_message = cls._log
        cls.server.shutdown()
        cls.server.server_close()

    # -- helpers ---------------------------------------------------------

    def _request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res, json.loads(data) if data else None

    def _post(self, path, payload=None):
        return self._request("POST", path, json.dumps(payload if payload is not None else {}))

    def _reset(self):
        res, payload = self._post("/api/scenario", {"key": "visual-orbit-demo"})
        self.assertEqual(res.status, 200)
        res, _ = self._post("/api/clock/reset")
        self.assertEqual(res.status, 200)
        return payload

    def _snapshot(self):
        res, payload = self._request("GET", "/api/snapshot")
        self.assertEqual(res.status, 200)
        return payload

    def _clock(self):
        res, payload = self._request("GET", "/api/clock")
        self.assertEqual(res.status, 200)
        return payload

    def _advance_for(self, scale: float, seconds: float) -> float:
        """Reset to epoch, run at ``scale`` for ``seconds`` of wall time, pause."""
        self._reset()
        res, _ = self._post("/api/clock/time_scale", {"time_scale": scale})
        self.assertEqual(res.status, 200)
        res, _ = self._post("/api/clock/resume")
        self.assertEqual(res.status, 200)
        time.sleep(seconds)
        res, paused = self._post("/api/clock/pause")
        self.assertEqual(res.status, 200)
        self.assertTrue(paused["paused"])
        return paused["simulation_time_s"]

    def _wait_until_running(self, timeout_s=2.0):
        # reset parks the clock at the paused epoch, so start it explicitly.
        res, _ = self._post("/api/clock/resume")
        self.assertEqual(res.status, 200)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._clock()["simulation_time_s"] > 0.0:
                return
            time.sleep(0.05)
        self.fail("the clock never advanced after resume")

    # -- pause / resume ---------------------------------------------------

    def test_pause_freezes_simulated_time_and_state(self):
        self._reset()
        self._wait_until_running()
        res, paused = self._post("/api/clock/pause")
        self.assertEqual(res.status, 200)
        self.assertTrue(paused["paused"])

        first = self._snapshot()
        frozen_at = first["clock"]["simulation_time_s"]
        self.assertGreater(frozen_at, 0.0)
        time.sleep(0.35)
        second = self._snapshot()

        # Paused means no clock tick may mutate time or any satellite position.
        self.assertEqual(second["clock"]["simulation_time_s"], frozen_at)
        self.assertEqual(second["satellites"], first["satellites"])

    def test_resume_continues_from_the_frozen_time(self):
        self._reset()
        self._wait_until_running()
        res, paused = self._post("/api/clock/pause")
        frozen_at = paused["simulation_time_s"]

        time.sleep(0.2)
        self.assertEqual(self._clock()["simulation_time_s"], frozen_at, "paused time drifted")

        res, resumed = self._post("/api/clock/resume")
        self.assertEqual(res.status, 200)
        self.assertFalse(resumed["paused"])
        self.assertGreaterEqual(resumed["simulation_time_s"], frozen_at)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and self._clock()["simulation_time_s"] <= frozen_at:
            time.sleep(0.05)
        self.assertGreater(self._clock()["simulation_time_s"], frozen_at)

    def test_pause_and_resume_are_idempotent(self):
        self._reset()
        res, first = self._post("/api/clock/pause")
        self.assertEqual(res.status, 200)
        res, again = self._post("/api/clock/pause")
        self.assertEqual(res.status, 200)
        self.assertEqual(again["paused"], first["paused"])
        self.assertEqual(again["simulation_time_s"], first["simulation_time_s"])

        res, running = self._post("/api/clock/resume")
        self.assertEqual(res.status, 200)
        res, running_again = self._post("/api/clock/resume")
        self.assertEqual(res.status, 200)
        self.assertFalse(running["paused"])
        self.assertFalse(running_again["paused"])
        self.assertGreaterEqual(running_again["simulation_time_s"], running["simulation_time_s"])

    # -- reset ------------------------------------------------------------

    def test_reset_restores_the_exact_epoch_snapshot(self):
        self._reset()
        res, _ = self._post("/api/clock/time_scale", {"time_scale": 200})
        self.assertEqual(res.status, 200)
        self._post("/api/clock/resume")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and self._clock()["simulation_time_s"] < 1.0:
            time.sleep(0.05)
        self._post("/api/clock/pause")
        moved = self._snapshot()
        self.assertGreater(moved["clock"]["simulation_time_s"], 0.0)

        res, reset = self._post("/api/clock/reset")
        self.assertEqual(res.status, 200)
        self.assertEqual(reset["simulation_time_s"], 0.0)
        self.assertTrue(reset["paused"])
        self.assertEqual(reset["time_scale"], builtin_scenario("visual-orbit-demo").time_scale)

        expected = initial_snapshot(builtin_scenario("visual-orbit-demo")).to_dict()
        self.assertEqual(self._snapshot(), expected)

    # -- single step ------------------------------------------------------

    def test_repeated_step_advances_one_second_each_and_never_unpauses(self):
        self._reset()
        res, _ = self._post("/api/clock/time_scale", {"time_scale": 500})
        self.assertEqual(res.status, 200)

        config = builtin_scenario("visual-orbit-demo")
        for expected_t in (1.0, 2.0, 3.0):
            res, stepped = self._post("/api/clock/step")
            self.assertEqual(res.status, 200)
            self.assertEqual(stepped["simulation_time_s"], expected_t)
            self.assertTrue(stepped["paused"], "a step must not start the clock")
            self.assertEqual(stepped["time_scale"], 500, "a step must not change the scale")

            snapshot = self._snapshot()
            self.assertEqual(snapshot["clock"]["simulation_time_s"], expected_t)
            expected = snapshot_at_time(config, expected_t, snapshot_clock(snapshot)).to_dict()
            self.assertEqual(snapshot["satellites"], expected["satellites"])

        # The same one-second step keeps working after a reset.
        self._post("/api/clock/reset")
        res, stepped = self._post("/api/clock/step")
        self.assertEqual(stepped["simulation_time_s"], 1.0)

    # -- time scale -------------------------------------------------------

    def test_time_scale_changes_simulated_advance_not_rendering(self):
        slow = self._advance_for(1.0, 0.4)
        fast = self._advance_for(20.0, 0.4)

        # A paused, reset clock starts at zero and only moves while running.
        self.assertGreater(slow, 0.15, f"1x clock barely moved: {slow}")
        self.assertLess(slow, 2.0, f"1x clock ran far too fast: {slow}")
        # 20x must measurably outrun 1x over the same wall time. The advance loop
        # ticks every 100 ms, so a loose factor keeps this robust on slow CI.
        self.assertGreater(fast, slow * 5.0, f"20x ({fast}) did not outrun 1x ({slow})")
        self.assertEqual(self._clock()["time_scale"], 20.0)

    def test_invalid_time_scales_are_rejected_and_leave_the_clock_alone(self):
        self._reset()
        res, _ = self._post("/api/clock/time_scale", {"time_scale": 42})
        self.assertEqual(res.status, 200)
        before = self._clock()

        for invalid in (0, -1, -0.5, "60", True, None):
            res, payload = self._post("/api/clock/time_scale", {"time_scale": invalid})
            self.assertEqual(res.status, 400, f"{invalid!r} was accepted")
            self.assertEqual(payload["error"], "invalid_time_scale")
            self.assertIn("request_id", payload)

        after = self._clock()
        self.assertEqual(after["time_scale"], before["time_scale"])
        self.assertEqual(after["simulation_time_s"], before["simulation_time_s"])

    def test_absurd_time_scale_is_clamped_to_the_documented_bound(self):
        self._reset()
        res, clock = self._post("/api/clock/time_scale", {"time_scale": 5_000_000})
        self.assertEqual(res.status, 200)
        self.assertEqual(clock["time_scale"], 1_000_000)

        res, clock = self._post("/api/clock/time_scale", {"time_scale": 1e-9})
        self.assertEqual(res.status, 200)
        self.assertEqual(clock["time_scale"], 0.001)
        self._reset()


def snapshot_clock(snapshot: dict):
    """A paused clock at the snapshot's own time, for expected-state comparisons."""
    from constellab_core.contract import SimulationClock

    raw = snapshot["clock"]
    return SimulationClock(
        epoch_utc=raw["epoch_utc"],
        simulation_time_s=raw["simulation_time_s"],
        time_scale=raw["time_scale"],
        paused=raw["paused"],
    )


if __name__ == "__main__":
    unittest.main()
