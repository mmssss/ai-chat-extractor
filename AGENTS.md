# AI Chat Extractor - Project Context

## Project Overview

A tool that extracts AI coding assistant conversations from their local storage
formats and converts them to clean, readable files.

## Development Workflow

1. Ensure code passes flake8 linting (max-line-length=100)
2. Use `uv run` to run commands (handles venv automatically)
3. Test manually before committing
4. Never add "Co-Authored-By" or similar AI attribution lines to commits

## Testing Commands

```bash
# Install deps
uv sync --group dev

# Run tests
uv run pytest tests/ -v

# Lint check
uv run flake8 src/ --max-line-length=100
```

## Important Notes

- No external dependencies (uses only Python stdlib)
- Supports Python 3.10+
- Cross-platform (Windows, macOS, Linux)
- Read-only access to conversation files
