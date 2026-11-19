"""Run the ten-agent two-peer versus self-revision pilot."""

import sys

sys.dont_write_bytecode = True

from experiments.architecture_pilots.runner import main


if __name__ == "__main__":
    raise SystemExit(main(preset='sparse_peer'))
