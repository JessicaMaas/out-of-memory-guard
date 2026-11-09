import unittest

from out_of_memory_guard import MemoryGuard


class FakeMemory:
    """Deterministic memory reader for tests."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


class MemoryGuardTests(unittest.TestCase):
    def test_disables_when_below_threshold(self) -> None:
        mem = FakeMemory(100)
        guard = MemoryGuard(mem, threshold_bytes=200, resume_bytes=400)
        guard.register("a", lambda: None)
        guard.register("b", lambda: None)
        self.assertTrue(guard.check())
        self.assertTrue(guard.is_disabled("a"))
        self.assertTrue(guard.is_disabled("b"))

    def test_enables_when_above_resume(self) -> None:
        mem = FakeMemory(100)
        guard = MemoryGuard(mem, threshold_bytes=200, resume_bytes=400)
        guard.register("a", lambda: None)
        guard.check()
        mem.value = 500
        self.assertFalse(guard.check())
        self.assertFalse(guard.is_disabled("a"))

    def test_hysteresis_between_thresholds(self) -> None:
        mem = FakeMemory(100)
        guard = MemoryGuard(mem, threshold_bytes=200, resume_bytes=400)
        guard.register("a", lambda: None)
        guard.check()
        mem.value = 300
        self.assertTrue(guard.check())
        mem.value = 500
        self.assertFalse(guard.check())
        mem.value = 300
        self.assertFalse(guard.check())

    def test_resume_below_threshold_raises(self) -> None:
        with self.assertRaises(ValueError):
            MemoryGuard(FakeMemory(0), threshold_bytes=100, resume_bytes=50)

    def test_unregister_removes_from_disabled(self) -> None:
        mem = FakeMemory(0)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        guard.register("a", lambda: None)
        guard.check()
        self.assertTrue(guard.is_disabled("a"))
        guard.unregister("a")
        self.assertFalse(guard.is_disabled("a"))

    def test_register_replaces_handler(self) -> None:
        mem = FakeMemory(0)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        calls = []
        guard.register("a", lambda: calls.append(1))
        guard.register("a", lambda: calls.append(2))
        mem.value = 300
        guard.run_handlers()
        self.assertEqual(calls, [2])

    def test_run_handlers_skips_disabled(self) -> None:
        mem = FakeMemory(0)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        calls = []
        guard.register("a", lambda: calls.append("a"))
        guard.register("b", lambda: calls.append("b"))
        guard.check()
        ran = guard.run_handlers()
        self.assertEqual(ran, [])
        self.assertEqual(calls, [])

    def test_run_handlers_order(self) -> None:
        mem = FakeMemory(300)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        calls = []
        guard.register("a", lambda: calls.append("a"))
        guard.register("b", lambda: calls.append("b"))
        ran = guard.run_handlers()
        self.assertEqual(ran, ["a", "b"])
        self.assertEqual(calls, ["a", "b"])

    def test_run_essential_always_runs(self) -> None:
        mem = FakeMemory(0)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        guard.check()
        calls = []
        guard.run_essential(lambda: calls.append("essential"))
        self.assertEqual(calls, ["essential"])

    def test_threshold_boundary_is_disabled(self) -> None:
        mem = FakeMemory(100)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        guard.register("a", lambda: None)
        self.assertTrue(guard.check())

    def test_resume_boundary_is_enabled(self) -> None:
        mem = FakeMemory(200)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        guard.register("a", lambda: None)
        guard.check()
        self.assertFalse(guard.check())

    def test_check_returns_false_with_no_handlers(self) -> None:
        mem = FakeMemory(0)
        guard = MemoryGuard(mem, threshold_bytes=100, resume_bytes=200)
        self.assertFalse(guard.check())


if __name__ == "__main__":
    unittest.main()
