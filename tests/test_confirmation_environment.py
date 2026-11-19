"""Explicit pre-inference driver baseline and hardware identity checks."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.confirmation_pilot import environment


class ConfirmationEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(environment.EXPECTED_ENVIRONMENT)
        self.reference = copy.deepcopy(self.config["hardware_snapshot"])
        for key, difference in self.config["reference_differences"].items():
            self.reference[key] = difference["reference"]

    def test_explicit_driver_baseline_is_validated_without_mutating_input(self):
        original_config = copy.deepcopy(self.config)
        original_reference = copy.deepcopy(self.reference)
        result = environment.validate_environment(self.reference, self.config)
        self.assertEqual(result, original_config)
        self.assertIsNot(result, self.config)
        self.assertEqual(self.config, original_config)
        self.assertEqual(self.reference, original_reference)
        self.assertEqual(set(result["reference_differences"]), {"nvidia_gpu_and_driver"})
        self.assertTrue(result["amendment"]["declared_before_confirmation_inference"])
        self.assertEqual(result["amendment"]["existing_confirmation_generations"], 0)

    def test_other_hardware_changes_are_rejected_even_if_declared(self):
        changes = {
            "cpu": "Different CPU",
            "memory_bytes": self.reference["memory_bytes"] + 1024,
            "cpu_count": self.reference["cpu_count"] + 1,
            "platform": "Different OS",
            "hostname_sha256": "0" * 64,
        }
        for key, value in changes.items():
            changed = copy.deepcopy(self.config)
            changed["hardware_snapshot"][key] = value
            changed["reference_differences"][key] = {"reference": self.reference[key], "confirmation": value}
            with self.subTest(field=key), self.assertRaises(ValueError):
                environment.validate_environment(self.reference, changed)

    def test_gpu_model_memory_or_unparseable_identity_cannot_be_hidden_as_driver_change(self):
        gpu_key = "nvidia_gpu_and_driver"
        current = self.config["hardware_snapshot"][gpu_key]
        model, memory, driver = [piece.strip() for piece in current.split(",")]
        changed_values = [f"Different GPU, {memory}, {driver}",
                          f"{model}, 1 MiB, {driver}",
                          "unparseable GPU identity", None, ""]
        for value in changed_values:
            changed = copy.deepcopy(self.config)
            changed["hardware_snapshot"][gpu_key] = value
            changed["reference_differences"][gpu_key]["confirmation"] = value
            with self.subTest(gpu=value), self.assertRaises(ValueError):
                environment.validate_environment(self.reference, changed)

    def test_reference_hash_declared_difference_and_amendment_are_not_optional(self):
        cases = []
        bad_hash = copy.deepcopy(self.config)
        bad_hash["reference_hardware_sha256"] = "0" * 64
        cases.append(bad_hash)
        no_difference = copy.deepcopy(self.config)
        no_difference["reference_differences"] = {}
        cases.append(no_difference)
        wrong_difference = copy.deepcopy(self.config)
        wrong_difference["reference_differences"]["nvidia_gpu_and_driver"]["reference"] = "wrong reference"
        cases.append(wrong_difference)
        post_inference = copy.deepcopy(self.config)
        post_inference["amendment"]["existing_confirmation_generations"] = 1
        cases.append(post_inference)
        undeclared = copy.deepcopy(self.config)
        undeclared["amendment"]["declared_before_confirmation_inference"] = False
        cases.append(undeclared)
        unknown = copy.deepcopy(self.config)
        unknown["unfrozen_override"] = True
        cases.append(unknown)
        missing = copy.deepcopy(self.config)
        missing.pop("reference_hardware_sha256")
        cases.append(missing)
        for index, changed in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                environment.validate_environment(self.reference, changed)

    def test_loaded_environment_must_equal_frozen_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "environment.json"
            path.write_text(json.dumps(self.config), encoding="utf-8")
            with patch.object(environment, "ENVIRONMENT_PATH", path):
                result = environment.load_environment({"hardware_snapshot": self.reference})
                self.assertEqual(result, self.config)
                changed = copy.deepcopy(self.config)
                changed["environment_id"] += "-edited"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ValueError):
                    environment.load_environment({"hardware_snapshot": self.reference})


if __name__ == "__main__":
    unittest.main()
