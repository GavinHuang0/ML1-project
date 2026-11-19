"""Audit saved pilot traces and compare voting/stopping policies without inference."""

import sys

# A dry run must not create bytecode caches beside frozen source dependencies.
sys.dont_write_bytecode = True

from experiments.offline_policies.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
