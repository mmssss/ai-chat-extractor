# AI Chat Extractor

Extract AI coding assistants' conversations from local storage. Converts conversations to clean Markdown, JSON, or HTML files.

Currently supports **Claude Code** (`~/.claude/projects/`). **OpenAI Codex** support planned.

Forked from [claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor) by Dustin Kirby.

## Installation

```bash
git clone https://github.com/mmssss/ai-chat-extractor
cd ai-chat-extractor
pipx install .
```

If you want to tinker with this tool, you can install in editable mode:
```bash
pipx install --editable .
```

## Commands

| Command | Description |
|---------|-------------|
| `ai-extract` | Interactive UI when run bare, full CLI with flags |
| `ai-search` | Quick search across all conversations |

## Usage

```bash
# Interactive mode (recommended)
ai-extract

# List all conversations
ai-extract --list

# Export specific conversations by number
ai-extract --extract 1,3,5

# Export recent conversations
ai-extract --recent 5

# Export all conversations
ai-extract --all

# Save to custom location
ai-extract --output ~/my-backups

# Search conversations
ai-search "API integration"
```

### Export Formats

```bash
# Markdown (default)
ai-extract --extract 1

# JSON with metadata
ai-extract --format json --extract 1

# HTML with styling
ai-extract --format html --all

# Include tool use, system messages, MCP responses
ai-extract --detailed --extract 1
```

### Search

```bash
# Real-time interactive search
ai-search

# Direct search
ai-search "error handling"

# Search with filters
ai-extract --search "python" --search-date-from 2025-06-01
ai-extract --search-regex "import\s+\w+"
```

## Automatic Periodic Export (systemd)

The repo includes a systemd **timer + oneshot service** pair in `systemd/`
that runs incremental exports on a schedule (daily at 04:00 by default).

### Install

1. Copy units to your user systemd directory:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/ai-chat-extractor.{service,timer} ~/.config/systemd/user/
   ```

2. Optionally edit the output directory (default: `~/claude-logs`):
   ```bash
   vim ~/.config/systemd/user/ai-chat-extractor.service
   ```

3. Enable and start the timer:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now ai-chat-extractor.timer
   ```

### Verify

```bash
# Check the timer is active
systemctl --user list-timers ai-chat-extractor.timer

# Run once manually to test
systemctl --user start ai-chat-extractor.service

# View logs
journalctl --user -u ai-chat-extractor.service
```

### Change schedule

Edit `~/.config/systemd/user/ai-chat-extractor.timer` and change `OnCalendar=`:

```ini
OnCalendar=*-*-* 04:00:00     # once a day at 04:00 (default)
OnCalendar=hourly              # every hour
OnCalendar=*-*-* 06,18:00:00  # twice a day at 06:00 and 18:00
```

Then reload: `systemctl --user daemon-reload`.

## Where Conversations Are Stored

| Provider | Location | Format |
|----------|----------|--------|
| Claude Code | `~/.claude/projects/*/chat_*.jsonl` | JSONL |
| Codex (planned) | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | JSONL |

## Privacy

- The tool runs entirely offline, never sends data anywhere
- Read-only access to conversation files

## Development setup

```bash
git clone https://github.com/mmssss/ai-chat-extractor
cd ai-chat-extractor
uv sync --group dev
```

```bash
# Run tests
uv run pytest tests/ -v

# Lint
uv run flake8 src/ --max-line-length=100
```

## License

MIT
