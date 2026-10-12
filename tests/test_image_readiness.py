"""Tests du contrôle de disponibilité DOM, indépendant de Selenium réel."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from image_readiness import wait_image_ready


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class FakeDriver:
    def __init__(self, states):
        self.states = iter(states)
        self.last = None

    def execute_script(self, script, element):
        try:
            self.last = next(self.states)
        except StopIteration:
            pass
        return self.last


class ImageReadinessTests(unittest.TestCase):
    def test_returns_after_two_identical_loaded_observations(self):
        state = {"loaded": True, "src": "blob:result", "width": 2048, "height": 1536}
        clock = FakeClock()
        driver = FakeDriver([state, state])
        ready, result = wait_image_ready(
            driver, object(), timeout=2.0, interval=0.1,
            clock=clock.clock, sleep=clock.sleep,
        )
        self.assertTrue(ready)
        self.assertEqual(result, state)
        self.assertLess(clock.now, 0.2)

    def test_waits_for_src_to_stabilize(self):
        low_res = {"loaded": True, "src": "blob:preview", "width": 512, "height": 384}
        final = {"loaded": True, "src": "blob:final", "width": 2048, "height": 1536}
        clock = FakeClock()
        driver = FakeDriver([low_res, final, final])
        ready, result = wait_image_ready(
            driver, object(), timeout=2.0, interval=0.1,
            clock=clock.clock, sleep=clock.sleep,
        )
        self.assertTrue(ready)
        self.assertEqual(result["src"], "blob:final")

    def test_reports_not_ready_when_image_never_loads(self):
        state = {"loaded": False, "src": "blob:pending", "width": 0, "height": 0}
        clock = FakeClock()
        driver = FakeDriver([state])
        ready, result = wait_image_ready(
            driver, object(), timeout=0.3, interval=0.1,
            clock=clock.clock, sleep=clock.sleep,
        )
        self.assertFalse(ready)
        self.assertIsNone(result)
        self.assertGreaterEqual(clock.now, 0.3)

    def test_uses_loaded_image_at_short_deadline_even_if_not_stable(self):
        state = {"loaded": True, "src": "blob:result", "width": 1024, "height": 768}
        clock = FakeClock()
        driver = FakeDriver([state])
        ready, result = wait_image_ready(
            driver, object(), timeout=0.0, clock=clock.clock, sleep=clock.sleep,
        )
        self.assertTrue(ready)
        self.assertEqual(result, state)


if __name__ == "__main__":
    unittest.main()
