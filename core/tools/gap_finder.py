#!/usr/bin/env python3
"""
SupremeAI Universal Gap Finder wrapper script.
Delegates to the newly split `tools.gap_finder` package.
"""

from gap_finder.cli import main

if __name__ == "__main__":
    main()
