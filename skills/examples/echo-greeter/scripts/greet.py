#!/usr/bin/env python3
"""Reference entry script for the echo-greeter skill."""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a greeting.")
    parser.add_argument("--name", default="world")
    args = parser.parse_args()
    print(f"Hello, {args.name}! — from the echo-greeter skill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
