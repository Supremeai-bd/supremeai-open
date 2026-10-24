#!/usr/bin/env python3
"""Repository-friendly entry point.

Place the `knowledge_squeezer` package under backend/ or another importable path,
then adjust PYTHONPATH as needed.
"""
import asyncio

from knowledge_squeezer.cli import main

if __name__ == "__main__":
    asyncio.run(main())
