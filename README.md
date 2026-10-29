# rc-files

Personal Linux shell configuration and standalone command-line tools, intended
for one machine rather than as a general-purpose package.

The Python scripts require **CPython 3.12 or newer** and use only the standard
library. Some tools invoke external commands, noted below. Poetry, Ruff, pytest
and prek are development tools, not runtime requirements for the scripts.

## Installation

Review [bashrc](bashrc) before replacing your shell configuration, then run from
the checkout:

```sh
./install.py
```

[install.py](install.py) creates these symlinks, creating parent directories as needed:

| Source                                 | Destination                           |
| -------------------------------------- | ------------------------------------- |
| [bashrc](bashrc)                       | ~/.bashrc                             |
| [passwdwords](passwdwords)             | ~/.passwdwords                        |
| Each file directly inside [bin/](bin/) | ~/bin/, with its final suffix removed |

For example, [bin/mkpass.py](bin/mkpass.py) becomes the command `mkpass`.
Subdirectories are not traversed. The installer links every direct file, not just
executable files, and **does not set executable permissions**. Keep the checkout
in place: these are links, not copies. Ensure ~/bin/ is on `PATH`.

- Correct existing links are left alone.
- Conflicting files or links stop installation with an error; earlier links may
  already have been created.
- `--force-links` replaces symlinks pointing elsewhere, including broken links.
- `--force-file` deletes conflicting regular files before linking; it makes no
  backup. Directories and other non-regular files are never replaced.

Use the overwrite flags only after inspecting the conflicts; they can be combined.
Run `python3 install.py --help` to inspect options without installing anything.

## Tools

Examples use the installed command names. All Python tools support `--help`.

### `disk_status`

[Source](bin/disk_status.py). Runs remote Linux `df` over `ssh`, reporting usage
per mount and highlighting values **above 90%**. Requires an SSH client, access
to the hosts and remote `df`; excludes several virtual filesystems, including
tmpfs and squashfs.

```sh
disk_status user@host1 host2
disk_status
```

With no hosts, reads ~/.disk_status: one SSH host specification per line, with
blank lines and text from `#` onwards ignored. SSH uses a five-second connection
timeout, not an overall command timeout.
SSH failures go to stderr, other hosts are still checked, and the command exits
non-zero if any SSH check fails. High usage alone does not change the exit status.

### `indirs`

[Source](bin/indirs.py). Runs **one quoted command string** in each directory:

```sh
indirs 'git status --short' project-a project-b
indirs --parallel=2 --no-shell 'git status --short' project-a project-b
indirs --if-exists pyproject.toml --if-exists poetry.lock 'poetry check' project-a project-b
```

- Default: sequential execution through the shell; quote the command to defer
  expansion until it runs inside each directory.
- `--no-shell`: splits the string with `shlex`, without shell expansion or pipes.
- `--if-exists FILE`: repeat to require **all** specified paths to exist before
  running in a directory. Relative paths are checked against each workdir, with
  no glob expansion; existing directories also count. Valid workdirs missing any
  required path are silently skipped without a header or failure status. Invalid
  workdirs still cause a reported failure.
- `--header`: prints the directory argument exactly as supplied (including `./`
  and trailing slashes) in green, followed by a colour reset, before its command
  output. Sequential headers are flushed before starting the command.
- `--parallel`: uses the CPU count; `--parallel=N` sets a positive worker count
  (use `=`, not a separate numeric argument). Each command's output is buffered
  until completion, then published in directory argument order as one block:
  optional header, stdout, stderr and any failure diagnostic. Stdout and stderr
  keep their separate channels; their original relative timing is not retained.
  Sequential execution continues to stream output without buffering.
- Invalid directories or failed commands cause a non-zero exit, but do not stop
  processing the other valid directories. `--` ends option parsing.

### `mkpass`

[Source](bin/mkpass.py). Generates three-word passphrases using `SystemRandom`,
random capitalisation and separators.

```sh
mkpass 3
mkpass
```

The optional **positional** positive count prints exactly that many passwords,
one per line. Without it, output fills a terminal-sized grid, reserving one row
for the prompt. Requires ~/.passwdwords with at least 4,096 distinct non-blank
entries after stripping whitespace; duplicates do not count towards the minimum.
`--help` does not load the dictionary.

### `mv_count`

[Source](bin/mv_count.py). Renames files in argument order using a numeric pattern:

```sh
mv_count --sandbox -n 10 -p 'photo-{:03d}.jpg' a.jpg b.jpg
mv_count -n 10 -p 'photo-{:03d}.jpg' a.jpg b.jpg
```

- `-p` / `--pattern`: Python format string, default `file-{}`.
- `-n` / `--start`: starting integer, default `1`.
- `-s` / `--sandbox`: validates and previews without changing files.
- `-f` / `--force`: permits overwriting existing destinations, including names
  occupied by other sources in the same plan. Unrelated overwritten data is
  discarded on success.

Relative destinations are relative to the current directory, not each source's
directory. Destination parents must already exist. Duplicate sources or
destinations, malformed patterns, directory sources and directory destinations
are rejected before moving anything; broken destination symlinks count as conflicts.

Sources are staged under temporary names so overlapping renames do not clobber
one another. Forced destinations are backed up until publication succeeds.
On an OS error, restoration is attempted; if restoration fails, the retained
data's location is reported. This is not an atomic transaction or a substitute
for backups. Moves across filesystems are not supported.

### `rot13`

[Source](bin/rot13.py). Transforms UTF-8 text with ROT13 (not encryption):

```sh
rot13 -s 'Hello'
printf 'Hello\n' | rot13
rot13 input.txt -o output.txt
```

Read from a positional file, `-` or stdin when omitted; `-s` / `--string` is
mutually exclusive with a positional input, even for an empty string.
`-o` / `--output` writes to a file, replacing its contents; default output is stdout.

### `ssl_checker`

[Source](bin/ssl_checker.py). Checks TLS certificates concurrently using the
default trust store and hostname verification:

```sh
ssl_checker --sort https://example.com example.org:8443
ssl_checker
```

Accepts URLs or bare hostnames with optional ports (default 443); bracket IPv6
addresses. It checks the TLS endpoint, not HTTP paths or responses. With no
arguments, reads ~/.ssl_checker_urls, one entry per line, ignoring blank lines
and text from `#` onwards. `-s` / `--sort` sorts input alphabetically, not by expiry.

Expiry is red at 10 days or fewer, yellow at 30 or fewer, otherwise green.
Malformed inputs, connection errors and certificate verification failures go to
stderr and cause a non-zero exit; successful results still appear on stdout.
Near-expiry colouring alone does not cause failure.

### `update_project`

[Source](bin/update_project.py). Run from the target project's directory. Requires
Git and at least one applicable updater installed on `PATH`:

```sh
update_project --dry-run
update_project --branch chore/update-deps-manual
```

- Poetry applies when both the project TOML and Poetry lockfile exist; runs
  `poetry update` and stages the lockfile only.
- Hooks use the first configuration found: prek.toml, .pre-commit-config.yaml,
  then .pre-commit-config.yml. Prefers `prek auto-update`, otherwise
  `pre-commit autoupdate`; TOML requires prek. The selected configuration is
  passed explicitly and staged.
- Missing or incompatible tools are skipped; no applicable updater means failure.

Normal execution requires a clean working tree (including untracked files),
creates a branch named `chore/update-deps-YYYY-MM-DD` unless `--branch` is given,
then updates, stages and commits with version-change details. No staged changes
means no commit, but the new branch remains. Nothing is pushed.

`--dry-run` reports the branch and applicable updaters without updating, creating
a branch or requiring a clean tree. Failed updates can leave the new branch and
partial changes behind; inspect and clean up manually.

Hook revision summaries for YAML configurations use simple line matching, not
a full YAML parser; do not rely on complete summaries for complex YAML layouts.

### `rebuild_bash_complete`

[Source](bin/rebuild_bash_complete.sh). Run `rebuild_bash_complete` with no arguments
to replace ~/.bash_completion with generated Bash completions for whichever of
Poetry, Ruff, Git LFS, uv and pip are installed. Requires Bash and the standard
`mktemp`, `mv` and `rm` utilities. Output is generated in a temporary file; a
generator failure leaves the existing completion file untouched. If none of the
generators is installed, the resulting file is empty.

## Shell configuration and completions

[bashrc](bashrc) sets `umask 0002`, history behaviour, a Git-aware prompt,
`EDITOR=vim` and a colourised `ls` alias. It adds ~/bin/ and ~/.local/bin/ to
`PATH`, then removes duplicate and empty entries. It initialises pyenv under
~/lib/pyenv and direnv **without checking they are installed**, and loads optional
~/.bashrc_local overrides. Review these machine-specific assumptions first.
The prompt calls `__git_ps1`, but its definition is only sourced if the configured
Git prompt helper exists; systems without that helper need a prompt override.

System Bash completion is sourced when available. The installer does not link
[bash_completions](bash_completions), the separate pip completion definitions,
or generate ~/.bash_completion. Loading the generated file depends on the system
completion setup; add an explicit source in ~/.bashrc_local if needed.

## Development and checks

[pyproject.toml](pyproject.toml) configures Poetry in non-package mode and lists
pytest, Ruff and prek as development dependencies. From the repository root,
install the development environment and both local Git hook types:

```sh
poetry install --with dev
poetry run prek install --config prek.toml --hook-type pre-commit --hook-type commit-msg
```

[prek.toml](prek.toml) is the shared repository configuration. The command above
installs both hook shims in this checkout; cloning the repository or installing
dependencies alone does not install them. Repeat hook installation for each
checkout, and keep Poetry available on `PATH` when committing. External hook
environments need downloading/preparing on first use.

The pre-commit hooks run:

- Built-in file hygiene, syntax, merge-conflict, private-key, shebang and
  large-file checks. Some hygiene hooks **modify files**; review their changes
  and stage them before retrying a failed commit.
- Official external Ruff hooks, pinned independently of the development Ruff
  dependency. `ruff-check` and `ruff-format --check` check matching Python files
  passed by prek, not the entire tree. Neither is configured to fix files.
- The full `poetry run pytest` suite via a local system hook, with no filenames
  passed. It is marked `always_run`, including for non-Python-only or empty
  commits.

The commit-msg hook validates Conventional Commits messages, for example
`docs: correct hook setup`. Installing only the pre-commit hook does not enable
this check.

Validate the configuration and run the pre-commit-stage hooks against all tracked
files (hygiene hooks may change them), or run the checks separately:

```sh
poetry run prek validate-config prek.toml
poetry run prek run --config prek.toml --stage pre-commit --all-files
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
git diff --check
```

The all-files command does not validate a commit message or include untracked
files. Separate Ruff commands check the whole tree using the development version.

[tests/](tests/) uses pytest fixtures, parametrised cases, temporary homes and
synthetic data. SSH, TLS and project-update command boundaries are mocked so
these tests do not contact real hosts or update projects.

The suite covers CLI validation and output, password dictionary handling,
file-renaming conflicts and rollback, hook configuration discovery and Git error
handling. Regressions run as ordinary tests, with no expected-failure markers;
assertions follow the current stderr, word-list and subprocess interfaces.
These are offline regression checks, not live SSH/TLS or updater integration
tests, and do not establish exhaustive correctness.

For focused development, pass a test path or node ID to `poetry run pytest`, or
use `-k` to select tests by name. Run the full suite before committing; the
installed pre-commit hook always runs it regardless of the files being committed.

The checks are independent: passing tests does not imply Ruff is clean. Ruff
enables all rules with explicit exceptions.
