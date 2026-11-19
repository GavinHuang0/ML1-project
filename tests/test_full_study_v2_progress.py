"""Measured ETA weighting, resume semantics and terminal output checks."""

import io
import unittest

from experiments.full_study_v2.progress import Progress


def position(index, kind="shared_initial", phase="development"):
    return {"phase": phase, "question_id": f"q{index}", "round": 0 if kind == "shared_initial" else 1,
            "agent_id": 0, "arm": kind}


class TTY(io.StringIO):
    def isatty(self):
        return True


class ProgressTests(unittest.TestCase):
    def test_initial_unknown_eta_and_completion_zero(self):
        bar = Progress([position(0), position(1)], clock=lambda: 10)
        self.assertIsNone(bar.estimate(0))
        self.assertIn("ETA estimating", bar.render(0))
        self.assertEqual(bar.estimate(2), 0)
        self.assertIn("100.0%", bar.render(2))
        for invalid in (-1, 3, 1.0, True):
            with self.assertRaises(ValueError):
                bar.render(invalid)

    def test_eta_weights_initial_communication_and_self_means_by_remaining_schedule(self):
        calls = [position(0), position(1, "communication"), position(2, "self_revision"),
                 position(3, "communication"), position(4, "self_revision")]
        bar = Progress(calls)
        for call, elapsed in zip(calls[:3], (2, 8, 4)):
            bar.record({**call, "elapsed_seconds": elapsed})
        self.assertEqual(bar.estimate(3), 12)
        self.assertIn("ETA 00:00:12", bar.render(3))

    def test_resume_uses_prior_durations_without_human_pause_in_elapsed(self):
        moments = iter((100, 105))
        calls = [position(0), position(1, "communication"), position(2, "self_revision")]
        old = [{**calls[0], "elapsed_seconds": 10}, {**calls[1], "elapsed_seconds": 30}]
        bar = Progress(calls, prior_records=old, clock=lambda: next(moments))
        # New class has no observations yet, so global mean20 estimates self.
        self.assertEqual(bar.estimate(2), 20)
        line = bar.render(2)
        self.assertIn("session 00:00:05", line)
        self.assertIn("ETA 00:00:20", line)

    def test_new_phase_falls_back_to_previous_phase_class_before_global(self):
        future = [position(2, "communication", "validation"), position(3, "self_revision", "validation")]
        prior = [{**position(0, "communication"), "elapsed_seconds": 9},
                 {**position(1, "self_revision"), "elapsed_seconds": 3}]
        bar = Progress(future, prior_records=prior)
        self.assertEqual(bar.estimate(0), 12)

    def test_duplicate_records_do_not_inflate_estimates_and_invalid_durations_fail(self):
        calls = [position(0), position(1)]
        bar = Progress(calls)
        record = {**calls[0], "elapsed_seconds": 2}
        bar.record(record)
        bar.record({**record, "elapsed_seconds": 100})
        self.assertEqual(bar.estimate(1), 2)
        for invalid in (-1, float("nan"), float("inf"), "2", True):
            with self.assertRaises(ValueError):
                bar.record({**calls[1], "elapsed_seconds": invalid})

    def test_nonterminal_logs_lines_and_terminal_updates_one_line_then_closes(self):
        calls = [position(0), position(1)]
        plain = io.StringIO()
        bar = Progress(calls, stream=plain, clock=lambda: 0)
        bar.display(0)
        bar.display(1)
        self.assertEqual(plain.getvalue().count("\n"), 2)
        self.assertNotIn("\r", plain.getvalue())
        tty = TTY()
        bar = Progress(calls, stream=tty, clock=lambda: 0)
        bar.display(0)
        bar.display(1, final=True)
        self.assertEqual(tty.getvalue().count("\r"), 2)
        self.assertEqual(tty.getvalue().count("\n"), 1)
        self.assertTrue(tty.getvalue().isascii())


if __name__ == "__main__":
    unittest.main()
