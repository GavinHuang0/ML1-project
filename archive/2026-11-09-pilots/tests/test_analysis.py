"""Ensure current posterior scores cannot silently reinterpret historical runs."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_results
from experiment_config import MODEL, SCORING_VERSION
import run_experiment


class FixtureClient:
    def __init__(self, **kwargs):
        pass

    def health(self):
        return {"version": "fixture", "models": [{"name": MODEL, "digest": "fixture"}]}

    def chat(self, model, messages, **kwargs):
        return {"model": model, "done": True, "done_reason": "stop",
                "message": {"content": '{"final_answer":"0.25","explanation":"Fixture."}'},
                "prompt_eval_count": 10, "eval_count": 10}


class AnalysisTests(unittest.TestCase):
    def test_posterior_v2_scores_survive_raw_recomputation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"current.jsonl"
            with patch.object(run_experiment, "OllamaClient", FixtureClient), redirect_stdout(io.StringIO()):
                self.assertEqual(run_experiment.main(["--output", str(path)]), 0)
            result = analyze_results.analyze(path)
            self.assertEqual(result["protocol"]["scoring_version"], SCORING_VERSION)
            self.assertEqual(result["actual_run"]["calls"], 60)
            for method in result["methods"].values():
                # 0.25 selects the historical correct state, but is far from both posteriors.
                sensor = method["families"]["evidence"]
                self.assertEqual(sensor["individual_correct"], 0)
                self.assertEqual(sensor["panel_correct"], 0)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[0]["protocol"]["scoring_version"] = "decision-v1"
            changed = Path(directory)/"wrong-version.jsonl"
            changed.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaisesRegex(ValueError, "archived analyzer"):
                analyze_results.analyze(changed)

    def test_historical_run_is_rejected_without_relabeling_scores(self):
        root = Path(__file__).resolve().parents[1]
        path = root/"archive/2026-10-24-legacy/results/experiment1-qwen-seed42-max512.jsonl"
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "archived analyzer"):
            analyze_results.analyze(path)
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
