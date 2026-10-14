"""Compatibility entry point; implementation lives in scripts.setup_models."""

import importlib
import sys

_impl = importlib.import_module("scripts.setup_models")

if __name__ == "__main__":
    raise SystemExit(_impl.main())
else:
    sys.modules[__name__] = _impl
