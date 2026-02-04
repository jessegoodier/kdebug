# AGENTS.md - AI Assistant Guide

This file helps AI coding assistants understand the kdebug project.

## Project Overview

kdebug is a Python CLI tool for launching ephemeral debug containers in Kubernetes pods. It provides interactive shell access, backup capabilities, and a TUI for pod selection.

## Project Structure

```
kdebug/
├── pyproject.toml           # Package metadata and build config (version source of truth)
├── src/
│   └── kdebug/
│       ├── __init__.py      # Package init with __version__ from importlib.metadata
│       └── cli.py           # Main CLI code
├── completions/
│   ├── kdebug.bash          # Bash completion script (generated)
│   └── _kdebug              # Zsh completion script (generated)
├── README.md                # User documentation
├── AGENTS.md                # This file
└── .github/
    └── workflows/
        └── release.yml      # Release automation (updates pyproject.toml)
```

## Key Architecture

- **Python package**: Installable via `uv tool install kdebug` or `pip install .`
- **Entry point**: `kdebug` command maps to `kdebug.cli:main`
- **Version**: Single source of truth in `pyproject.toml`, accessed via `importlib.metadata`
- **No external dependencies**: Uses Python stdlib only
- **Completion scripts are generated**: The functions `generate_bash_completion()` and `generate_zsh_completion()` in `src/kdebug/cli.py` produce the completion files
- **Global state pattern**: Module-level variables (`DEBUG_MODE`, `KUBECTL_CONTEXT`, `KUBECTL_KUBECONFIG`) are set after argument parsing

## Making Changes

### Adding a new CLI argument

1. Add the argument to the appropriate `parser.add_argument_group()` in `main()`
2. If it affects kubectl commands, update the relevant helper function or `kubectl_base_cmd()`
3. Update `generate_bash_completion()` - add to `opts` list and add completion case if needed
4. Update `generate_zsh_completion()` - add to `args` array with appropriate completer
5. Regenerate completion files (see below)
6. Update README.md if user-facing

### Modifying kubectl commands

All kubectl commands should use `kubectl_base_cmd()` to ensure `--context` and `--kubeconfig` are passed through:

```python
cmd = f"{kubectl_base_cmd()} get pods -n {namespace} -o json"
```

### Regenerating completion files

After modifying the completion generators:

```bash
# Install package in development mode first
uv pip install -e .

# Then regenerate completions
kdebug --completions bash > completions/kdebug.bash
kdebug --completions zsh > completions/_kdebug
```

## Testing

### Manual testing

```bash
# Install in development mode
uv pip install -e .

# Verify help output
kdebug --help

# Verify version
kdebug --version

# Test with debug mode to see kubectl commands
kdebug --debug -n <namespace>

# Test argument combinations
kdebug --context <ctx> --kubeconfig <path> -n <ns> --pod <pod>
```

### Syntax checks

```bash
# Python syntax
python3 -m py_compile src/kdebug/cli.py

# Bash completion syntax
bash -n completions/kdebug.bash

# Zsh completion syntax
zsh -n completions/_kdebug
```

### Testing completions

```bash
# Bash
source <(kdebug --completions bash)
kdebug --<TAB>

# Zsh
source <(kdebug --completions zsh)
kdebug --<TAB>
```

## GitHub Actions & Dependencies

**IMPORTANT: Always use the latest stable versions of GitHub Actions and dependencies to avoid security vulnerabilities (CVEs).**

### Current Action Versions (keep updated)

- `actions/checkout@v6`
- `astral-sh/setup-uv@v7`

### Guidelines

1. **Never hardcode old versions** - Check the action's repository for the latest major version
2. **Use major version tags** (e.g., `@v6`) not specific commits or minor versions
3. **Dependabot is configured** - Review and merge dependabot PRs promptly
4. **When adding new actions** - Always check for the latest version first via the action's GitHub repo or marketplace page

### Workflow Files

- `.github/workflows/release.yml` - Main release automation
- `.github/workflows/pypi-publish.yml` - PyPI publishing with OIDC trusted publisher
- `.github/workflows/update-homebrew.yml` - Homebrew tap updates

## Code Conventions

- Use `colorize()` for colored output
- Use `run_command()` for executing shell commands
- Use `print_debug_command()` to show commands when `--debug` is enabled
- Error messages go to stderr with `file=sys.stderr`
- Success indicators use green checkmarks: `{colorize('✓', Colors.GREEN)}`
- Error indicators use red X: `{colorize('✗', Colors.RED)}`

## Dependencies

- Python 3.8+ (for `importlib.metadata`)
- kubectl (must be in PATH and configured)
- No pip packages required

## Installation

```bash
# Via uv (recommended)
uv tool install kdebug

# Via pip
pip install .

# Development mode
uv pip install -e .
```
