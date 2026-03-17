# Claude Conversation Extractor - Project Context

## Project Overview

This is a standalone tool that extracts Claude Code conversations from the
undocumented JSONL format in `~/.claude/projects/` and converts them to clean
markdown files. This is the FIRST publicly available solution for this problem.

## Key Goals

- **Professional Quality**: This project needs to be polished and professional -
  it's important for the developer's family
- **Easy Installation**: Setting up PyPI publishing so users can
  `pip install claude-conversation-extractor`
- **Wide Adoption**: Make this the go-to solution for Claude Code users

## Repository Structure

```text
claude-conversation-extractor/
├── src/
│   ├── extract_claude_logs.py   # Orchestrator class + CLI entry point
│   ├── parsers.py               # JSONL parsing, content/text extraction
│   ├── metadata.py              # Session discovery, metadata extraction
│   ├── formatters.py            # Output formatting (md/json/html), filenames
│   ├── search_conversations.py  # Search engine (smart, exact, regex, semantic)
│   ├── interactive_ui.py        # Interactive terminal UI
│   ├── realtime_search.py       # Real-time search UI
│   └── search_cli.py            # claude-search entry point
├── tests/                       # Test suite
├── docs/                        # Documentation
├── pyproject.toml               # Package configuration & entry points
├── setup.py                     # Legacy packaging (PyPI)
├── README.md                    # Main documentation
└── LICENSE                      # MIT License
```

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
- **`search_cli.py`** — Lightweight `claude-search` entry point.

## Entry Points

All defined in `pyproject.toml` under `[project.scripts]`:
- `claude-extract` → `extract_claude_logs:launch_interactive` (primary command)
- `claude-search` → `search_cli:main` (dedicated search shortcut)
- `claude-start` / `claude-logs` → same as `claude-extract` (aliases)

## Development Workflow

1. Always create feature branches for new work
2. Ensure code passes flake8 linting (max-line-length=100)
3. When trying to run any python command/script (e.g. tests), activate the venv in the project root: `source .venv/bin/activate`
4. Test manually before committing
5. Update version numbers in setup.py for releases
6. Create detailed commit messages
7. Never add "Co-Authored-By" or similar AI attribution lines to commits

## Testing Commands

```bash
# Run tests
pytest

# Test extraction via installed commands
claude-extract --list
claude-extract --extract 1
claude-search "test query"

# Lint check
flake8 . --max-line-length=100

# Install in development mode
pip install -e .
```

## Important Notes

- No external dependencies (uses only Python stdlib)
- Supports Python 3.8+
- Cross-platform (Windows, macOS, Linux)
- Read-only access to Claude's conversation files
- Includes legal disclaimer for safety

## Version History

See [CHANGELOG.md](../user/CHANGELOG.md) for full version history.
