# AI Chat Extractor - Project Context

## Project Overview

A tool that extracts AI coding assistant conversations from their local storage
formats and converts them to clean, readable files. 

### Module Responsibilities

- **`extract_claude_logs.py`** — Thin orchestrator (`ClaudeConversationExtractor` class)
  that delegates to focused modules, plus CLI (`main()`) and `launch_interactive()`.
- **`parsers.py`** — Pure functions for JSONL content parsing: `extract_conversation()`,
  `extract_text_content()`, `get_conversation_preview()`, IDE preamble/slash-command cleanup.
- **`metadata.py`** — Session discovery and metadata: `find_sessions()`, `find_subagents()`,
  `extract_session_metadata()`, `get_subagent_metadata()`.
- **`formatters.py`** — Output formatting: `save_as_markdown()`, `save_as_json()`,
  `save_as_html()`, `slugify()`, `generate_filename()`.
- **`search_conversations.py`** — `ConversationSearcher` with pluggable matcher pattern
  and `SearchResult` dataclass.
- **`interactive_ui.py`** — Terminal UI with folder selection, session menu, search integration.
- **`realtime_search.py`** — Real-time search with keyboard handling and terminal display.
- **`search_cli.py`** — Lightweight `ai-search` entry point.

## Entry Points

All defined in `pyproject.toml` under `[project.scripts]`:
- `ai-extract` → `extract_claude_logs:launch_interactive` (primary command)
- `ai-search` → `search_cli:main` (dedicated search shortcut)

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
