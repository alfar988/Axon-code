#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Axion Code launcher.

    python run.py                 start in ~/workspace
    python run.py ~/projects/app  start in a folder of your choice
    python run.py --setup         enter the OpenRouter API key again
    python run.py --help          all options

Standard library only: Python 3.8 or newer is all you need.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if sys.version_info < (3, 8):
    sys.exit("Axion Code needs Python 3.8 or newer.")

from axion.cli import main  # noqa: E402
from axion.ui import out    # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        out()
        sys.exit(130)
