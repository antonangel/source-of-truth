#!/usr/bin/env python3
"""Deprecated shim: delegates to sot.py. Will be removed in the next release."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sot import *
import sot

def _main():
    sys.stderr.write("warning: fact-diff.py is deprecated; use 'sot.py diff' instead.\n")
    return sot.diff_main(sys.argv)

if __name__ == "__main__":
    sys.exit(_main())
