# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-10 - Fork & Rename

### Changed
- Forked from [claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor) v1.1.2
- Renamed project to ai-chat-extractor
- New entry points: `ai-extract`, `ai-search`
- Removed PyPI publishing wiring
- Simplified packaging and documentation
- Bumped minimum Python to 3.10

### Planned
- OpenAI Codex conversation support
- Provider abstraction for multiple AI assistants

---

## Prior History (upstream)

## [1.1.1] - 2025-08-28 - View Conversations & Better Search

### Added
- Conversation viewer in terminal without extracting files
- JSON and HTML export formats
- `--format` and `--detailed` flags
- `claude-search` command

### Fixed
- Missing `claude-logs` command in PyPI package
- Arrow key handling in real-time search
- Search functionality to view conversations instead of forcing extraction

## [1.1.0] - 2025-06-05 - Interactive UI

### Added
- Interactive UI for conversation extraction
- `claude-start` command
- `--interactive` / `-i` flag
- Batch export with progress tracking

## [1.0.0] - 2025-05-25 - Initial Release

### Added
- Extract conversations from Claude Code ~/.claude/projects JSONL files
- List, extract, search, and bulk export conversations
- Markdown output format
- Cross-platform support (Windows, macOS, Linux)
- Zero external dependencies
