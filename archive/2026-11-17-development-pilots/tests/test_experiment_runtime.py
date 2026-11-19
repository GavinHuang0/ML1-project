"""Portable lock and cooperative-pause checks without real model inference."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch
import types

from experiment_runtime import FileLock, PauseController


class RuntimeTests(unittest.TestCase):
    def test_file_lock_excludes_concurrent_resumes_and_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lock"
            with FileLock(path):
                with self.assertRaisesRegex(RuntimeError, "Another process"):
                    FileLock(path).acquire()
            with FileLock(path):
                pass

    def test_pause_request_survives_in_file_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pause"
            pause = PauseController(path)
            self.assertFalse(pause.requested())
            pause.request()
            self.assertTrue(PauseController(path).requested())
            pause.clear_request()
            self.assertFalse(path.exists())
            self.assertFalse(pause.requested())

    def test_windows_lock_backend_locks_one_byte_and_unlocks_on_close(self):
        events = []
        backend = types.SimpleNamespace(LK_NBLCK=11, LK_UNLCK=12,
                                        locking=lambda fd, mode, count: events.append((mode, count)))
        with tempfile.TemporaryDirectory() as temporary:
            lock = FileLock(Path(temporary) / "windows-lock")
            with patch("experiment_runtime.os.name", "nt"), patch.dict("sys.modules", {"msvcrt": backend}):
                lock.acquire()
                lock.close()
            self.assertEqual(events, [(11, 1), (12, 1)])

    def test_first_interrupt_requests_checkpoint_second_interrupt_forces_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous = signal.getsignal(signal.SIGINT)
            with PauseController(Path(temporary) / "pause") as pause, redirect_stderr(io.StringIO()):
                pause._handle(signal.SIGINT, None)
                self.assertTrue(pause.requested())
                with self.assertRaises(KeyboardInterrupt):
                    pause._handle(signal.SIGINT, None)
            self.assertEqual(signal.getsignal(signal.SIGINT), previous)


if __name__ == "__main__":
    unittest.main()
