# kdebug development tasks
# Run `just` to see available recipes

# Install dependencies and project in dev mode
setup:
    uv sync

# Run tests
test *args:
    uv run pytest {{args}}

# Run tests with verbose output
test-v *args:
    uv run pytest -v {{args}}

# Lint with ruff
lint:
    uv run ruff check src/ tests/

# Format with ruff
format:
    uv run ruff format src/ tests/

# Check formatting without making changes
format-check:
    uv run ruff format --check src/ tests/

# Run all checks (lint + format check + tests)
check: lint format-check test

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix src/ tests/

# Build the package
build:
    uv build

# Show help output for all subcommands
help:
    uv run kdebug --help
    @echo ""
    @echo "--- debug subcommand ---"
    @echo ""
    uv run kdebug debug --help
    @echo ""
    @echo "--- backup subcommand ---"
    @echo ""
    uv run kdebug backup --help

# Verify shell completion scripts parse correctly
check-completions:
    bash -n src/kdebug/completions/kdebug.bash
    zsh -n src/kdebug/completions/_kdebug
    @echo "Completion scripts OK"

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

audit-app:
    # only audit main app
    uv sync --active
    uv run scripts/audit_dependencies.py
audit-dev:
    # audit dev dependencies
    uv sync --all-extras --active
    uv run scripts/audit_dependencies.py