"""Shared settings and provenance for the active calculator baseline."""

import hashlib
from pathlib import Path
import subprocess
import sys


MODEL = "llama3.2:3b"
MAX_TOKENS = 1024
TEMPERATURE = 0.7
CONTEXT_TOKENS = 4096
EXPLANATION_WORD_LIMIT = 60
PROBABILITY_TOLERANCE = 0.001
PROBABILITY_ROUNDOFF = 1e-15
SCORING_VERSION = "calculator-delivery-v1"
PROTOCOL_VERSION = "calculator-baseline-v1"
EXECUTION_PROTOCOL_VERSION = "planner-calculator-v1"
ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ("experiment_config.py", "calculator.py", "calculator_protocol.py",
                "local_llm.py", "setup_models.py", "run_baseline.py",
                "config/models.json", "config/baseline.json")


def protocol_metadata():
    return {"version": PROTOCOL_VERSION, "model": MODEL, "max_tokens": MAX_TOKENS,
            "execution_protocol": EXECUTION_PROTOCOL_VERSION,
            "temperature": TEMPERATURE, "context_tokens": CONTEXT_TOKENS,
            "explanation_word_limit": EXPLANATION_WORD_LIMIT,
            "scoring_version": SCORING_VERSION,
            "probability_tolerance": PROBABILITY_TOLERANCE,
            "probability_roundoff": PROBABILITY_ROUNDOFF,
            "sensor_headline": "absolute_posterior_error_within_tolerance",
            "model_output_fields": ["explanation", "expression"],
            "answer_origin": "deterministic_calculator",
            "calculator": "restricted_exact_rational_arithmetic_v1",
            "reference_free_execution": True,
            "model_feedback": False, "repairs": False, "retries": False,
            "strict_correctness_requires_complete_method": True}


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
