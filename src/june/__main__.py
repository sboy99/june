"""Allow `python -m june`."""

import sys

from june.interfaces.cli import main

sys.exit(main())
