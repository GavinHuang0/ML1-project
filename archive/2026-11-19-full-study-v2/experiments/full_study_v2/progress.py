"""ASCII progress with measured, resume-aware request-time estimates."""

from collections import defaultdict
import math
import sys
import time


def _category(position):
    return position.get("phase", "unknown"), ("initial" if position["round"] == 0 else position["arm"])


def _duration(seconds):
    if seconds is None:
        return "estimating"
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class Progress:
    """ETA covers outstanding model requests, not reporting or future pauses.

    A class uses its phase-local measured mean when available, then the same
    request class from earlier phases, then the global measured mean. Resumed
    records contribute durations without adding human pause time to elapsed.
    """

    def __init__(self, positions, prior_records=(), stream=None, clock=time.monotonic):
        self.positions = list(positions)
        self.total = len(self.positions)
        if self.total <= 0:
            raise ValueError("Progress requires a nonempty call schedule")
        self.stream = stream if stream is not None else sys.stdout
        self.clock = clock
        self.started = clock()
        self.samples = defaultdict(list)
        self.seen = set()
        self.last_completed = 0
        self._line_open = False
        for record in prior_records:
            self.record(record)

    def record(self, answer):
        elapsed = answer.get("elapsed_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("ETA samples need finite nonnegative measured request durations")
        identity = (answer.get("phase"), answer.get("question_id"), answer.get("round"),
                    answer.get("agent_id"), answer.get("arm"))
        if identity in self.seen:
            return
        self.seen.add(identity)
        self.samples[_category(answer)].append(float(elapsed))

    def estimate(self, completed):
        if type(completed) is not int or not 0 <= completed <= self.total:
            raise ValueError("Completed calls must be within the schedule")
        if completed == self.total:
            return 0.0
        all_samples = [value for samples in self.samples.values() for value in samples]
        if not all_samples:
            return None
        global_mean = sum(all_samples) / len(all_samples)
        result = 0.0
        for position in self.positions[completed:]:
            phase, kind = _category(position)
            candidates = self.samples.get((phase, kind))
            if not candidates:
                candidates = [value for (past_phase, past_kind), values in self.samples.items()
                              if past_kind == kind for value in values]
            result += sum(candidates) / len(candidates) if candidates else global_mean
        return result

    def render(self, completed, *, phase=None):
        remaining = self.estimate(completed)
        elapsed = max(0, self.clock() - self.started)
        width = 24
        filled = int(width * completed / self.total)
        bar = "#" * filled + "-" * (width - filled)
        label = phase if phase is not None else (self.positions[min(completed, self.total - 1)].get("phase", "study"))
        return (f"[{bar}] {completed}/{self.total} {100 * completed / self.total:5.1f}% "
                f"{label} | session {_duration(elapsed)} | ETA {_duration(remaining)} "
                "(model requests; estimate)")

    def display(self, completed, *, phase=None, final=False):
        line = self.render(completed, phase=phase)
        tty = bool(getattr(self.stream, "isatty", lambda: False)())
        if tty:
            self.stream.write("\r" + line + " " * 8)
            self._line_open = True
            if final or completed == self.total:
                self.stream.write("\n")
                self._line_open = False
        else:
            self.stream.write(line + "\n")
        self.stream.flush()
        self.last_completed = completed
        return line

    def close(self):
        if self._line_open:
            self.stream.write("\n")
            self.stream.flush()
            self._line_open = False
