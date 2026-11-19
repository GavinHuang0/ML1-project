"""Explicit pre-inference driver amendment for this confirmation only.

The reference experiment keeps its original environment. The fresh pilot
records the updated driver as a separate, strictly pinned runtime baseline.
"""

import copy
from pathlib import Path

from run_format_followup import canonical, snapshot_hash, strict_json


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_PATH = ROOT / "config/confirmation_environment.json"
_REFERENCE_HARDWARE = {
    "platform": "Windows-11-10.0.26200-SP0", "architecture": "AMD64", "cpu_count": 16,
    "cpu": "AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD",
    "memory_bytes": 33514393600,
    "hostname_sha256": "05923234c2ba44a773036d74cefb6f4b01c6daa0186e82d6d0403796207c232d",
    "nvidia_gpu_and_driver": "NVIDIA GeForce RTX 4070 SUPER, 12282 MiB, 617.42",
}
_CONFIRMATION_HARDWARE = {
    **_REFERENCE_HARDWARE,
    "nvidia_gpu_and_driver": "NVIDIA GeForce RTX 4070 SUPER, 12282 MiB, 621.24",
}
EXPECTED_ENVIRONMENT = {
    "schema_version": 1, "environment_id": "confirmation-driver-baseline-621.24-v1",
    "reference_hardware_sha256": snapshot_hash(_REFERENCE_HARDWARE),
    "hardware_snapshot": _CONFIRMATION_HARDWARE,
    "reference_differences": {
        "nvidia_gpu_and_driver": {
            "reference": _REFERENCE_HARDWARE["nvidia_gpu_and_driver"],
            "confirmation": _CONFIRMATION_HARDWARE["nvidia_gpu_and_driver"],
        },
    },
    "amendment": {
        "declared_before_confirmation_inference": True,
        "existing_confirmation_generations": 0,
        "reason": "NVIDIA driver updated from 617.42 to 621.24 on the same PC and GPU before any confirmation calls; record an independent environment baseline and retain strict within-run identity checks.",
    },
}


def validate_environment(reference_hardware, environment_config):
    required = {"schema_version", "environment_id", "reference_hardware_sha256",
                "hardware_snapshot", "reference_differences", "amendment"}
    if (not isinstance(environment_config, dict) or set(environment_config) != required
            or environment_config["schema_version"] != 1
            or not isinstance(environment_config["environment_id"], str)
            or not environment_config["environment_id"]):
        raise ValueError("Invalid confirmation environment configuration")
    if snapshot_hash(reference_hardware) != environment_config["reference_hardware_sha256"]:
        raise ValueError("Reference hardware hash differs from the declared environment amendment")
    current = environment_config["hardware_snapshot"]
    if (not isinstance(current, dict) or set(current) != set(_REFERENCE_HARDWARE)
            or not isinstance(reference_hardware, dict) or set(reference_hardware) != set(current)):
        raise ValueError("Hardware snapshot fields differ from the complete frozen identity")
    changes = {key: {"reference": reference_hardware[key], "confirmation": current[key]}
               for key in current if reference_hardware[key] != current[key]}
    if changes != environment_config["reference_differences"] or set(changes) != {"nvidia_gpu_and_driver"}:
        raise ValueError("Only the explicitly declared pre-run NVIDIA driver change is permitted")
    old_gpu, new_gpu = (reference_hardware["nvidia_gpu_and_driver"], current["nvidia_gpu_and_driver"])
    if not isinstance(old_gpu, str) or not isinstance(new_gpu, str):
        raise ValueError("GPU identity and driver must be present")
    before, after = old_gpu.rsplit(",", 1), new_gpu.rsplit(",", 1)
    if (len(before) != 2 or len(after) != 2 or before[0] != after[0]
            or not before[1].strip() or not after[1].strip() or before[1].strip() == after[1].strip()):
        raise ValueError("GPU model and memory must match; only its driver version may change")
    amendment = environment_config["amendment"]
    if (not isinstance(amendment, dict)
            or amendment.get("declared_before_confirmation_inference") is not True
            or type(amendment.get("existing_confirmation_generations")) is not int
            or amendment["existing_confirmation_generations"] != 0
            or not isinstance(amendment.get("reason"), str) or not amendment["reason"]):
        raise ValueError("Driver amendment must be declared before any confirmation inference")
    return copy.deepcopy(environment_config)


def load_environment(reference):
    config = strict_json(ENVIRONMENT_PATH.read_text(encoding="utf-8"))
    if canonical(config) != canonical(EXPECTED_ENVIRONMENT):
        raise ValueError("Environment differs from the explicitly frozen driver baseline")
    return validate_environment(reference["hardware_snapshot"], config)
