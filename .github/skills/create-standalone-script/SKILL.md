---
name: create-standalone-script
description: "Use when asked to add, create, or write a new standalone script in this repository."
---

# Create a standalone script

Use this workflow for one new script in this repository. Do not use it to scaffold a project or edit an existing script.

1. Inspect relevant examples in `bin/` and follow their naming and interface patterns where appropriate. Existing scripts are not fully uniform; treat the repository instructions as the preferred standard.
2. Establish the requested behaviour and target platform. Keep the script suitable for personal use on Linux; Python scripts target CPython 3.12 or newer and use only the standard library at runtime.
3. Add the script directly under `bin/`. Follow `.github/copilot-instructions.md` for the relevant language conventions, CLI parsing, and error handling.
4. Account for installation: `install.py` handles files immediately inside `bin/` only, links them into `~/bin/`, and removes the final filename suffix. It does not set executable permissions; do not imply otherwise.
5. Implement only the requested behaviour. Validate syntax and run focused checks for the requested behaviour; report the checks and any limitations.
