# Development Guide

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [just](https://github.com/casey/just) (command runner)
- `kubectl` configured with cluster access (for manual testing)

## Getting Started

```bash
# Install dev dependencies and project in editable mode
just setup
```

This runs `uv sync`, which creates a `.venv/`, installs the project in editable mode, and installs dev dependencies (pytest, ruff).

## Common Tasks

Run `just` with no arguments to see all available recipes.

```bash
just setup             # Install dependencies
just check             # Run all checks (lint + format + tests)
just test              # Run tests
just test-v            # Run tests with verbose output
just test-v -k cluster # Run specific tests by keyword
just lint              # Lint with ruff
just fmt               # Format with ruff
just fmt-check         # Check formatting without changes
just lint-fix          # Auto-fix lint issues
just build             # Build the package
just help              # Show CLI help for all subcommands
just check-completions # Verify shell completion scripts parse
just clean             # Remove build artifacts
```

## Project Structure

```
src/kdebug/
  __init__.py              # Package init, __version__ from importlib.metadata
  cli.py                   # All CLI code (~1400 lines)
  completions/
    kdebug.bash            # Bash tab completion
    _kdebug                # Zsh tab completion
tests/
  test_cluster_validation.py
  test_container_uid.py
```

## Tooling

| Tool | Purpose | Config |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Package management, virtualenv, running commands | `pyproject.toml` |
| [pytest](https://docs.pytest.org/) | Test runner | `[tool.pytest.ini_options]` in `pyproject.toml` |
| [ruff](https://docs.astral.sh/ruff/) | Linting and formatting | `[tool.ruff]` in `pyproject.toml` |
| [just](https://github.com/casey/just) | Task runner | `justfile` |

All tool configuration lives in `pyproject.toml`:

```toml
[dependency-groups]
dev = ["pytest>=7.0", "ruff>=0.4"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
ignore = ["E501"]
```

E501 (line length) is ignored because the codebase has many long colorized f-strings that are clearer on a single line.

## Running Commands Directly

If you prefer not to use `just`, all commands go through `uv run`:

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run kdebug --help
```

## Config File

kdebug reads defaults from `~/.config/kdebug/kdebug.json` (respects `XDG_CONFIG_HOME`). Useful for development with a lightweight debug image:

```json
{
  "debugImage": "busybox:latest",
  "cmd": "sh"
}
```

See the main [README](README.md#config-file) for all config keys.

## Architecture Notes

- **Single-file CLI**: All logic lives in `src/kdebug/cli.py`
- **No external deps**: Only Python stdlib + kubectl
- **Global state**: `DEBUG_MODE`, `KUBECTL_CONTEXT`, `KUBECTL_KUBECONFIG` are module-level globals set after arg parsing
- **Subcommands**: `debug` (default) and `backup`, implemented via `argparse.add_subparsers()`
- **Shared args on main parser**: So bare `kdebug --pod foo` works without typing `debug`
