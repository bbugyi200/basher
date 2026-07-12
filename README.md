# basher

[![CI](https://github.com/bbugyi200/basher/actions/workflows/ci.yml/badge.svg)](https://github.com/bbugyi200/basher/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/basher.svg)](https://pypi.org/project/basher/)
[![Python versions](https://img.shields.io/pypi/pyversions/basher.svg)](https://pypi.org/project/basher/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`basher` vendors shell scripts and the `bugyi.sh` Bash library into projects. It
keeps provenance beside every artifact, replaces stale copies safely, updates
references without regular-expression surprises, and makes freshness visible to
both humans and CI.

The original `pyvendor` script used date-stamped filenames for everything and
depended on a dotfiles checkout. `basher` packages the library, gives library
copies meaningful version suffixes, retains compatible handling for legacy
artifacts, and adds dry runs, layered configuration, status reporting, and rich
terminal output.

## Install

Python 3.11 or newer is required. Installing as a standalone tool keeps basher's
dependencies out of your project:

```bash
uv tool install basher
basher --version
```

Upgrade later with `uv tool upgrade basher`.

## Quick start

Vendor a script into a project:

```bash
basher vendor ~/bin/my-script /path/to/project
```

If the script contains the exact line `source ~/lib/bugyi.sh`, basher also
vendors its packaged library and rewrites the source line to a path relative to
the vendored script. A script is executable after vendoring, even when its source
mode was not.

When `PROJECT` is omitted, basher uses the enclosing Git repository root, or the
current directory when outside a Git repository:

```bash
cd /path/to/project
basher status
basher update --dry-run
basher update
```

To use the packaged library without vendoring it into a project:

```bash
source "$(basher path)"
# or materialize the conventional per-user copy:
basher export ~/lib
```

## Commands

Global options must appear before the command:

- `--version` prints the installed basher version.
- `-v`, `--verbose` prints the resolved project and artifact directories for
  mutating project commands.
- `-q`, `--quiet` suppresses non-error output.
- `--color {auto,always,never}` controls rich styling. `auto` follows terminal
  detection, and `NO_COLOR` selects `never` unless a higher-precedence setting
  overrides it.

### `basher vendor SCRIPT [PROJECT]`

Copies `SCRIPT` to `PROJECT/tools/<name>-<YYMMDD>`, removes stale copies, and
rewrites literal references to removed filenames throughout the project. Files
inside `CHEZMOI_SOURCE_ROOT` (default `~/.local/share/chezmoi`) lose a leading
`executable_` filename prefix. When the script sources `~/lib/bugyi.sh`, the
library is bundled unless `--no-lib` is set.

- `-t DIR`, `--tools-dir DIR`: script destination relative to the project
  (default `tools`).
- `-l DIR`, `--lib-dir DIR`: library destination relative to the project
  (default `lib`).
- `--no-lib`: do not bundle or rewrite the library source line.
- `--suffix TEXT`: override the script date suffix and, when bundled, the
  library version suffix.
- `-n`, `--dry-run`: show copies, removals, reference rewrites, and unified
  diffs without writing anything.
- `--force`: allow removal or replacement of files that do not carry a
  recognized provenance line.

### `basher lib [PROJECT]`

Vendors or refreshes only the packaged library. The destination is
`PROJECT/lib/bugyi-<BASHER_VERSION>.sh`. It removes legacy date-stamped and old
version-stamped copies and rewrites their literal filename references.

- `-l DIR`, `--lib-dir DIR`: library destination relative to the project.
- `--suffix TEXT`: override the package-version suffix.
- `-n`, `--dry-run`: preview the complete operation without writes.
- `--force`: permit replacing an unrecognized existing copy.

### `basher update [PROJECT]`

Finds recognized vendored artifacts and refreshes stale ones. Modern script
provenance contains the source path, so the script can be re-vendored. A legacy
library is refreshed from the packaged copy; a legacy script has no recoverable
source path and is skipped with a warning.

- `-t DIR`, `--tools-dir DIR`: directory to scan for scripts.
- `-l DIR`, `--lib-dir DIR`: directory to scan for the library.
- `-n`, `--dry-run`: preview the refresh and diffs without writes.
- `--force`: permit replacement of artifacts without recognized provenance.

An already-current project is a successful no-op.

### `basher status [PROJECT]`

Shows each recognized artifact's kind, vendored version or date, latest value,
and state. It exits with status 3 if any artifact is stale, legacy, or has a
missing source.

- `-t DIR`, `--tools-dir DIR`: directory to scan for scripts.
- `-l DIR`, `--lib-dir DIR`: directory to scan for the library.
- `--json`: emit a stable object with `project`, `stale`, and `artifacts` fields
  instead of the rich table. Each artifact reports `artifact`, `kind`, `source`,
  `vendored_date`, `vendored_version`, `latest`, `state`, and `legacy`.

### `basher cat`

Prints the raw packaged `bugyi.sh` to standard output without adding a
provenance line.

### `basher path`

Prints the filesystem path of the packaged `bugyi.sh`, suitable for
`source "$(basher path)"`.

### `basher export [DESTINATION]`

Writes an executable, unversioned `bugyi.sh` with basher provenance into
`DESTINATION` (default `~/lib`). Existing identical content is left untouched.

## Configuration

Basher resolves its three settings from lowest to highest precedence:

1. Built-in defaults: `tools_dir = "tools"`, `lib_dir = "lib"`, and
   `color = "auto"`.
2. User config at `${XDG_CONFIG_HOME:-~/.config}/basher/config.toml`.
3. `[tool.basher]` in the project `pyproject.toml`, then `.basher.toml` in the
   project root.
4. `BASHER_TOOLS_DIR`, `BASHER_LIB_DIR`, and `BASHER_COLOR`; `NO_COLOR` acts as
   `BASHER_COLOR=never` when that variable is unset.
5. Command-line flags.

User and `.basher.toml` files use top-level keys:

```toml
tools_dir = "vendor/tools"
lib_dir = "vendor/lib"
color = "auto"
```

The project `pyproject.toml` uses a table:

```toml
[tool.basher]
tools_dir = "vendor/tools"
lib_dir = "vendor/lib"
color = "never"
```

Directory values must be non-empty relative paths without `..`. Unknown keys,
invalid values, and malformed TOML are errors rather than silent fallbacks.

## Filenames and compatibility

Vendored scripts use a `-YYMMDD` suffix because scripts do not carry their own
versions. Vendored library copies use the basher package version, such as
`bugyi-0.2.0.sh`. `--suffix` provides an escape hatch for either scheme.

Cleanup recognizes the old `bugyi-YYMMDD.sh`/`bugyi_*.sh` names and current
versioned names. Project-wide reference updates use literal string replacement,
skip binary files and `.git`, and report every rewritten file.

Basher writes a machine-readable comment immediately after the shebang, or on
line one when no shebang exists:

```text
# Vendored by basher v<VERSION> from <SOURCE> on <YYYY-MM-DD>. Run 'basher update' to refresh.
```

Script sources are absolute paths with the home directory abbreviated to `~`.
The library source is `https://github.com/bbugyi200/basher`.

The legacy pyvendor comment is also recognized:

```text
# Vendored from https://github.com/bbugyi200/dotfiles via pyvendor on <YYYY-MM-DD>
```

Legacy library copies can be migrated automatically. Legacy script comments do
not contain an original path, so `status` marks those scripts as `legacy` and
`update` asks you to re-vendor them manually.

## Exit codes

- `0`: success, including an already-current no-op.
- `1`: runtime, filesystem, or configuration error.
- `2`: command-line usage error from argument parsing.
- `3`: `status` found at least one non-current artifact.

## `bugyi.sh` reference

The library has a double-source guard, exports `TZ=America/New_York`, and exposes
the following public helpers:

- `die [-x N|--exit-code N] MESSAGE [FORMAT_ARGS...]` logs an error and exits;
  the default code is 1. Code 2 adds command-line parsing guidance.
- `log::debug`, `log::info`, `log::warn`, and `log::error` accept printf-style
  arguments and `-u N`/`--up N` for caller traversal. Messages include caller
  metadata, go to standard error, and are sent to syslog with `logger`.
  `log::debug` honors `DEBUG=true` or `VERBOSE>0`; `DISABLE_LOG_COLOR=true`
  disables log coloring.
- `pyprintf FORMAT [ARGS...]` applies Python `str.format` syntax without adding
  a newline.
- `urlencode STRING [SAFE_CHARS]` percent-encodes a string while preserving the
  optional safe characters.
- `usage` prints one usage line per entry in the caller-provided
  `USAGE_GRAMMAR` array.

Sourcing the library defines `BUGYI_VERSION`, `BUGYI_HAS_BEEN_SOURCED`,
`SCRIPTNAME`, `MY_SHELL`, `COLOR_GREEN`, `COLOR_PURPLE`, `COLOR_RED`,
`COLOR_YELLOW`, `COLOR_RESET`, `XDG_RUNTIME`, `XDG_CONFIG`, `XDG_DATA`, and the
script-scoped `MY_XDG_RUNTIME`, `MY_XDG_CONFIG`, and `MY_XDG_DATA` paths.
`pyprintf` and `urlencode` require `python3`; logging uses standard Unix tools
including `logger`, `perl`, and `tee`.

## Development

The project uses [uv](https://docs.astral.sh/uv/) and
[just](https://just.systems/):

```bash
just install       # create .venv and install the package with dev tools
just fmt           # format and apply safe lint fixes
just fmt-check     # verify formatting
just lint          # ruff, strict mypy, symvision, toobig, and shellcheck
just test          # pytest with branch coverage and the 95% gate
just check         # all formatting, lint, shell, and test gates
```

Set `BASHER_PYTHON` to select the interpreter used for the virtual environment,
for example `BASHER_PYTHON=3.14 just check`. CI checks Python 3.11 through 3.14.

Releases are managed by release-please. Conventional commit and pull-request
titles determine version bumps, and published wheels are installed and exercised
in a fresh environment before trusted PyPI publishing.

## License

basher is released under the [MIT License](LICENSE).
