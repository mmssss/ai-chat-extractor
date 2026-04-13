# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.0] - 2026-04-13 - Codex Support & Source Adapter

### Added
- **OpenAI Codex support** — extract and search Codex CLI conversations (`~/.codex/sessions/`)
- **Source adapter registry** — extensible `SourceAdapter` dataclass for dispatching across AI assistants; adding a new source requires only a `*_parsers.py` + `*_metadata.py` pair
- `ai-chat-rsync` entry point — rsync helper for syncing conversation data from remote machines
- systemd service and timer for automated remote sync
- `--source-dir` flag to specify a custom source directory for export
- Content-based filenames for exported conversations
- Subagent extraction support (Claude and Codex)
- Skip already-exported conversations on re-run
- Seconds-precision timestamps in exports

### Fixed
- Markdown heading collisions when multiple conversations share a title
- Separator ambiguity in multi-conversation exports

### Changed
- Package restructured under `src/ai_chat_extractor/`
- Internal modules unified behind the adapter pattern (`parsers` / `metadata` per source)

## [0.1.0] - 2026-04-10 - Fork & Rename

### Changed
- Forked from [claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor) v1.1.2
- Renamed project to ai-chat-extractor
- New entry points: `ai-extract`, `ai-search`
- Removed PyPI publishing wiring
- Simplified packaging and documentation
- Bumped minimum Python to 3.10

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
