"""Run the selected five-agent full-study v2. Legacy v1 is preserved separately."""

import sys
sys.dont_write_bytecode = True

from experiments.full_study_v2.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
