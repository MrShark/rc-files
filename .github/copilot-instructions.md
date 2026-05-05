# Copilot Instructions

This repository is a personal collection of standalone scripts and configuration files.
The guidelines below apply to all files here.

## Purpose and scope

- Scripts are for **personal use** on a single machine. They do not need to be
  general-purpose, configurable for other users, or portable beyond Linux +
  CPython ≥ 3.12.
- Prefer **robust** over **general**: validate inputs, fail fast with clear
  messages, but do not over-engineer edge cases that will never occur in
  practice.
- Do **not** add features that were not asked for.
- Don't add comments that explain what the code is doing; the code should be clear
  enough on its own. Add comments only for non-obvious design decisions or
  trade-offs.
- Don't add type annotations that don't add value; if the code is already clear, they are
  just noise. Add type annotations only when they clarify intent or catch
  potential bugs.
- Never add noqa suppressions. Leave that for the user to decide.

## Python version

Target **Python 3.12 or newer**. Use modern syntax freely:
- `tomllib` (stdlib), `pathlib`, `f-strings`, structural pattern matching, etc.

## Stdlib only — no third-party dependencies

Every script must be **self-contained and runnable without installing anything**:
- Use only the Python standard library.
- HTTP via `urllib.request`, TOML via `tomllib`, CLI via `argparse`.
- For colour output, hardcode ANSI escape codes as named string constants.
- Do not add entries to `[tool.poetry.dependencies]` unless explicitly asked.

## File structure

- Always include `#!/usr/bin/env python3`.
- Always include a module-level docstring; add a `Usage:` block when the script
  accepts arguments.
- Always define `main()` and guard it with `if __name__ == "__main__":`.

## CLI

- Use `argparse` for all argument parsing.
- Use `sys.exit(msg)` or `raise SystemExit(msg)` for fatal user-visible errors
  — no tracebacks for expected failures.

## Error handling

- Print errors to `stderr`: `print(msg, file=sys.stderr)`.
- Use `raise SystemExit(msg)` (with a `msg` variable to satisfy ruff `TRY003`)
  for unrecoverable errors.
- Catch only the specific exceptions you expect.
- Do not define custom exception classes unless there is a strong reason.

## Subprocess calls

- Pass commands as `list[str]`, never as a shell string.
