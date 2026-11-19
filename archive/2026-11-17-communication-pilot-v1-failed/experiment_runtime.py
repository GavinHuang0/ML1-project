"""Portable experiment locks, hardware fingerprints, and cooperative pausing."""

import ctypes
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys

from run_multi_agent import snapshot_hash


class FileLock:
    def __init__(self, path):
        self.path, self.handle = Path(path), None

    def acquire(self):
        self.handle = self.path.open("a+b")
        try:
            self.handle.seek(0, 2)
            if not self.handle.tell():
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Another process holds this experiment's lock; do not launch concurrent resumes") from exc
        return self

    def close(self):
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()


class PauseController:
    """The first Ctrl+C waits for a durable call checkpoint; a second forces exit."""

    def __init__(self, request_file=None):
        self.request_file = Path(request_file) if request_file is not None else None
        self._requested, self._signals, self._previous = False, 0, None

    def request(self):
        self._requested = True
        if self.request_file is not None:
            self.request_file.touch(exist_ok=True)

    def requested(self):
        return self._requested or (self.request_file is not None and self.request_file.exists())

    def clear_request(self):
        self._requested = False
        self._signals = 0
        if self.request_file is not None:
            self.request_file.unlink(missing_ok=True)

    def _handle(self, signum, frame):
        self._signals += 1
        if self._signals > 1:
            raise KeyboardInterrupt
        self.request()
        print("\nPause requested. Waiting for the current model call to be saved. "
              "A second Ctrl+C forces interruption.", file=sys.stderr, flush=True)

    def __enter__(self):
        self._previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle)
        return self

    def close(self):
        if self._previous is not None:
            signal.signal(signal.SIGINT, self._previous)
            self._previous = None

    def __exit__(self, *_):
        self.close()


def hardware_identity():
    def command(arguments):
        try:
            result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=10)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    memory, cpu = None, platform.processor() or None
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        *[(name, ctypes.c_ulonglong) for name in
                          ("total_physical", "available_physical", "total_page", "available_page",
                           "total_virtual", "available_virtual", "available_extended")]]
        state = MemoryStatus()
        state.length = ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            memory = state.total_physical
    elif platform.system() == "Darwin":
        value = command(["sysctl", "-n", "hw.memsize"])
        memory = int(value) if value and value.isdigit() else None
        cpu = command(["sysctl", "-n", "machdep.cpu.brand_string"]) or cpu
    else:
        try:
            memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            pass
    gpu = command(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    return {"platform": platform.platform(), "architecture": platform.machine(),
            "cpu_count": os.cpu_count(), "cpu": cpu, "memory_bytes": memory,
            "hostname_sha256": snapshot_hash(platform.node()), "nvidia_gpu_and_driver": gpu}
