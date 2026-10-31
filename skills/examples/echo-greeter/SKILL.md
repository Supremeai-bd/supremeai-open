---
name: echo-greeter
version: 0.1.0
description: Reference skill demonstrating the SKILL.md contract with a script entry point.
triggers: [greet, hello, greeter]
entry: scripts/greet.py
---

# Echo Greeter

Prints a greeting, optionally personalized. Demonstrates the minimal
skill package layout: this frontmatter plus `scripts/greet.py`.

## Instructions

1. Run the entry script with an optional `--name <who>` argument.
2. Surface the script's stdout to the caller verbatim.
3. On non-zero exit, report stderr without retrying.
