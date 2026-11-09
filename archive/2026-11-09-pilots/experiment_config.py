"""Versioned settings for the sole active Llama experiment protocol."""

import hashlib
from pathlib import Path
import subprocess
import sys


MODEL = "llama3.2:3b"
MAX_TOKENS = 1024
PROBABILITY_TOLERANCE = 0.001
PROBABILITY_ROUNDOFF = 1e-15
SCORING_VERSION = "posterior-v2"
PROTOCOL_VERSION = "llama-1024-posterior-v2"
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ("experiment_config.py", "benchmark.py", "local_llm.py",
                "setup_models.py", "run_experiment.py", "run_pilots.py",
                "pilot_scoring.py", "analyze_results.py", "config/models.json",
                "config/pilots.json")


def protocol_metadata():
    return {"version": PROTOCOL_VERSION, "model": MODEL, "max_tokens": MAX_TOKENS,
            "scoring_version": SCORING_VERSION,
            "probability_tolerance": PROBABILITY_TOLERANCE,
            "probability_roundoff": PROBABILITY_ROUNDOFF,
            "sensor_headline": "absolute_posterior_error_within_tolerance",
            "sensor_panel_aggregation": "median_of_valid_posteriors",
            "urn_panel_aggregation": "rounded_plurality_then_original_median"}


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_FILES}


def generation_metadata():
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=False)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, text=True, check=False)
    return {"git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
            "git_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
            "source_sha256": source_hashes(), "python_version": sys.version}
