"""Compatibility entry point; implementation lives in experiments.communication_pilot.run."""

import importlib
import sys

_impl = importlib.import_module("experiments.communication_pilot.run")

if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl
