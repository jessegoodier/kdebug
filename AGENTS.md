# AGENTS.md - AI Assistant Guide

This file helps AI coding assistants understand the kdebug project.

## Project Overview

kdebug is a Python CLI tool for launching ephemeral debug containers in Kubernetes pods. It provides interactive shell access, backup capabilities, and a TUI for pod selection.

## Project Structure

```
kdebug/
├── bin/kdebug           # Main Python script (single-file application)
├── completions/
│   ├── kdebug.bash      # Bash completion script (generated)
│   └── _kdebug          # Zsh completion script (generated)
├── README.md            # User documentation
└── AGENTS.md            # This file
```

## Key Architecture

- **Single-file design**: All code lives in `bin/kdebug` - no external dependencies beyond Python stdlib
- **Completion scripts are generated**: The functions `generate_bash_completion()` and `generate_zsh_completion()` in `bin/kdebug` produce the completion files
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
./bin/kdebug --completions bash > completions/kdebug.bash
./bin/kdebug --completions zsh > completions/_kdebug
```

## Testing

### Manual testing

```bash
# Verify help output
./bin/kdebug --help

# Test with debug mode to see kubectl commands
./bin/kdebug --debug -n <namespace>

# Test argument combinations
./bin/kdebug --context <ctx> --kubeconfig <path> -n <ns> --pod <pod>
```

### Syntax checks

```bash
# Python syntax
python3 -m py_compile bin/kdebug

# Bash completion syntax
bash -n completions/kdebug.bash

# Zsh completion syntax
zsh -n completions/_kdebug
```

### Testing completions

```bash
# Bash
source <(./bin/kdebug --completions bash)
kdebug --<TAB>

# Zsh
source <(./bin/kdebug --completions zsh)
kdebug --<TAB>
```

## Code Conventions

- Use `colorize()` for colored output
- Use `run_command()` for executing shell commands
- Use `print_debug_command()` to show commands when `--debug` is enabled
- Error messages go to stderr with `file=sys.stderr`
- Success indicators use green checkmarks: `{colorize('✓', Colors.GREEN)}`
- Error indicators use red X: `{colorize('✗', Colors.RED)}`

## Dependencies

- Python 3.6+
- kubectl (must be in PATH and configured)
- No pip packages required
