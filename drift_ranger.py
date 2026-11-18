#!/usr/bin/env python3
"""Checkout shim: ``python drift_ranger.py <command> ...`` runs the packaged CLI.

The implementation lives in ``src/drift_ranger/cli.py``; the installed ``drift-ranger``
command and ``python -m drift_ranger`` run the same ``main``.
"""

import sys
from importlib import import_module
from pathlib import Path

if __name__ == "__main__":
    # Put this checkout's package ahead of this file, which shares its name.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    raise SystemExit(import_module("drift_ranger.cli").main())
