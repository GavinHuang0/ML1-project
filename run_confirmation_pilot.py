"""Run the prespecified twelve-question voting/stopping confirmation pilot."""

import sys

sys.dont_write_bytecode = True

from experiments.confirmation_pilot.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
