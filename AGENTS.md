# AGENTS.md - AI Assistant Guide

This file helps AI coding assistants work effectively in the `kdebug` repository.

## Project Overview

`kdebug` is a Python CLI for launching ephemeral Kubernetes debug containers and copying files out of pods. It supports:

- Interactive debug sessions
- Backup/copy workflows
- Rich-based terminal menus for pod selection
- Shell completion for bash, zsh, and fish

## Project Structure

```text
kdebug/
├── pyproject.toml                 # Package metadata, dependencies, version source of truth
├── justfile                       # Common development tasks
├── README.md                      # User-facing documentation
├── README-development.md          # Contributor/development guide
├── AGENTS.md                      # This file
├── docs/                          # Demo assets used by the README
├── scripts/
│   └── audit_dependencies.py      # Local dependency audit helper
├── src/
│   └── kdebug/
│       ├── __init__.py            # Exposes __version__ via importlib.metadata
│       ├── cli.py                 # Main argument parsing, selection flow, kubectl helpers
│       ├── debug.py               # Interactive exec/session behavior
│       ├── backup.py              # Backup path/template handling and copy logic
│       └── completions/
│           ├── __init__.py
│           ├── kdebug.bash        # Bash completion script
│           ├── _kdebug            # Zsh completion script
│           └── kdebug.fish        # Fish completion script
├── tests/
│   ├── test_backup.py
│   ├── test_cluster_validation.py
│   └── test_container_uid.py
└── .github/
    └── workflows/
        ├── release.yml
        ├── pypi-publish.yml
        ├── test.yml
        └── update-homebrew.yml
```

## Key Architecture

- **Entry point**: `kdebug` maps to `kdebug.cli:main`
- **Versioning**: version is defined in `pyproject.toml`; runtime reads it via `importlib.metadata`
- **Dependencies**: standard library plus `rich`
- **CLI shape**: `debug` and `backup` subcommands, with bare `kdebug` defaulting to `debug`
- **Global kubectl state**: `DEBUG_MODE`, `KUBECTL_CONTEXT`, and `KUBECTL_KUBECONFIG` are set after argument parsing
- **Completion delivery**: completion scripts are checked into `src/kdebug/completions/` and emitted via `importlib.resources` in `_output_completion_script()`
- **Module split**: argument parsing and cluster selection live in `cli.py`; subcommand implementations live in `debug.py` and `backup.py`

## Working In This Repo

### Adding or changing CLI arguments

1. Update the relevant parser setup in [`src/kdebug/cli.py`](/home/jesse/git-jesse/kdebug/src/kdebug/cli.py).
2. If the option affects kubectl invocations, route those commands through `kubectl_base_cmd()`.
3. If the option is shared, update both the main parser and the shared parent parser used by subcommands.
4. Update shell completion scripts under [`src/kdebug/completions/`](/home/jesse/git-jesse/kdebug/src/kdebug/completions).
5. Update [`README.md`](/home/jesse/git-jesse/kdebug/README.md) for any user-facing behavior changes.
6. Add or adjust tests when behavior changes.

### Modifying kubectl commands

All kubectl calls should preserve `--context` and `--kubeconfig` passthrough:

```python
cmd = f"{kubectl_base_cmd()} get pods -n {namespace} -o json"
```

### Shell completions

- Completion scripts are static files in [`src/kdebug/completions/`](/home/jesse/git-jesse/kdebug/src/kdebug/completions).
- `kdebug --completions bash|zsh|fish` reads those packaged files and prints them.
- If completions change, keep the checked-in files updated and validate them with the existing dev checks.

## Testing

### Preferred commands

```bash
just test
just check
just check-completions
```

### Direct commands

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
python3 -m py_compile src/kdebug/cli.py src/kdebug/debug.py src/kdebug/backup.py
bash -n src/kdebug/completions/kdebug.bash
zsh -n src/kdebug/completions/_kdebug
```

### Manual smoke checks

```bash
uv run kdebug --help
uv run kdebug debug --help
uv run kdebug backup --help
uv run kdebug --version
uv run kdebug --completions bash >/dev/null
uv run kdebug --completions zsh >/dev/null
uv run kdebug --completions fish >/dev/null
```

Cluster-dependent manual testing examples:

```bash
uv run kdebug --verbose -n <namespace>
uv run kdebug --context <ctx> --kubeconfig <path> -n <ns> --pod <pod>
uv run kdebug backup --pod <pod> --container-path /path/in/container
```

## Code Conventions

- Use `console.print()` and `err_console.print()` for terminal output
- Use `run_command()` for shell command execution unless a real interactive subprocess is required
- Use `print_debug_command()` for verbose kubectl visibility
- Route kubectl invocations through `kubectl_base_cmd()`
- Keep error output on stderr
- Prefer existing Rich styles and panels instead of introducing ad hoc color helpers

## Dependencies and Requirements

- Python 3.9+
- `kubectl` available in `PATH`
- A Kubernetes cluster that supports ephemeral containers for debug workflows
- Python package dependency: `rich>=14.0`

## GitHub Actions

Workflow files currently present:

- [`release.yml`](/home/jesse/git-jesse/kdebug/.github/workflows/release.yml)
- [`pypi-publish.yml`](/home/jesse/git-jesse/kdebug/.github/workflows/pypi-publish.yml)
- [`test.yml`](/home/jesse/git-jesse/kdebug/.github/workflows/test.yml)
- [`update-homebrew.yml`](/home/jesse/git-jesse/kdebug/.github/workflows/update-homebrew.yml)

Current action versions used in-repo:

- `actions/checkout@v6`
- `actions/setup-python@v6`
- `astral-sh/setup-uv@v7`

When touching workflows, keep action majors current and consistent with the repo's existing patterns.
