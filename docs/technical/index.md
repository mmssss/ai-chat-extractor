# Export Claude Code Conversations - The Only Tool That Works

## Can't Export Your Claude Code Chats? We Have The Solution.

Claude Code stores all your AI programming conversations in `~/.claude/projects/` but provides **NO export button**. Your valuable AI pair programming sessions are trapped in undocumented JSONL files.

**Claude Conversation Extractor** is the first and only tool that exports Claude Code conversations to clean, readable markdown files.

## 🚀 Export Claude Code in 30 Seconds

```bash
# Install the Claude export tool
pipx install claude-conversation-extractor

# Export your Claude conversations
claude-extract
```

That's it! The tool automatically finds all your Claude Code logs and lets you:
- 🔍 **Search** through all Claude conversations in real-time
- 📁 **Export** individual, recent, or all Claude sessions
- 💾 **Backup** your Claude Code logs before they're lost
- 📝 **Convert** Claude JSONL to clean markdown

## Why You Need to Export Claude Code Conversations

### The Problem with Claude Code
- ❌ No built-in export functionality
- ❌ Conversations stored in obscure JSONL format
- ❌ Located in hidden `~/.claude/projects` folder
- ❌ Risk of losing valuable AI programming sessions
- ❌ Can't share Claude conversations with team
- ❌ No way to search past Claude chats

### What Our Tool Does
- ✅ **Finds** all Claude Code conversations automatically
- ✅ **Extracts** from undocumented JSONL format
- ✅ **Converts** to clean, readable markdown
- ✅ **Searches** through all your Claude history
- ✅ **Exports** with proper formatting and timestamps
- ✅ **Works** on Windows, macOS, and Linux

## Features - Export Claude Code Like a Pro

### 🔍 Real-Time Search
Search your entire Claude Code history as you type. No flags, no commands - just start typing and see results instantly.

### 📦 Bulk Export
Export all your Claude conversations at once with `claude-extract --all`. Perfect for backing up before uninstalling or switching machines.

### 🎯 Smart Selection
Interactive UI lets you select exactly which Claude sessions to export. See dates, sizes, and preview content.

### 🚀 Zero Dependencies
Pure Python implementation - no external packages required. If Python runs, this tool runs.

### 🖥️ Cross-Platform
Works wherever Claude Code works - Windows, macOS, Linux. Same commands, same results.

## How to Export Claude Code Conversations

### Quick Start
```bash
# Interactive mode (recommended)
claude-extract

# List all conversations
claude-extract --list

# Export specific conversations
claude-extract --extract 1,3,5

# Export recent conversations
claude-extract --recent 10

# Export everything
claude-extract --all
```

### Where Are Claude Code Logs Stored?

**Default Claude Code locations:**
- macOS/Linux: `~/.claude/projects/*/chat_*.jsonl`
- Windows: `%USERPROFILE%\.claude\projects\*\chat_*.jsonl`

**After export:**
- Clean markdown files in `~/Desktop/Claude logs/`
- Or specify custom location with `--output`

## Installation Guide

### Recommended: Install with pipx
```bash
# macOS
brew install pipx
pipx ensurepath
pipx install claude-conversation-extractor

# Windows
py -m pip install --user pipx
py -m pipx ensurepath
pipx install claude-conversation-extractor

# Linux
sudo apt install pipx  # or dnf, pacman, etc.
pipx ensurepath
pipx install claude-conversation-extractor
```

### Alternative: Install with pip
```bash
pip install claude-conversation-extractor
```

## Frequently Asked Questions

### Q: How do I export Claude Code conversations?
A: Install our tool with `pipx install claude-conversation-extractor` then run `claude-extract`. It automatically finds and exports your conversations.

### Q: Where does Claude Code store conversations?
A: Claude Code saves chats in `~/.claude/projects/` as JSONL files. There's no built-in way to export them - that's why this tool exists.

### Q: Can I search my Claude Code history?
A: Yes! Run `claude-search` and start typing. Results appear in real-time.

### Q: Does this work with Claude.ai?
A: No, this tool is specifically for Claude Code (the desktop app). Claude.ai has its own export feature.

### Q: Is this tool official?
A: No, this is an independent open-source tool. It reads the local Claude Code files on your computer.

## User Testimonials

> "I thought I lost months of Claude conversations when I switched computers. This tool saved everything!" - Developer

> "Finally! I can search through my Claude history to find that solution from last week." - Data Scientist

> "Essential tool for anyone using Claude Code seriously. Should be built-in." - Software Engineer

## Get Started Now

Don't risk losing your Claude Code conversations. Install the extractor today:

```bash
pipx install claude-conversation-extractor
claude-extract
```

**Links:**
- [GitHub Repository](https://github.com/ZeroSumQuant/claude-conversation-extractor)
- [PyPI Package](https://pypi.org/project/claude-conversation-extractor/)
- [Report Issues](https://github.com/ZeroSumQuant/claude-conversation-extractor/issues)

---

**Keywords**: export claude code conversations, claude conversation extractor, claude code export tool, backup claude code logs, save claude chat history, claude jsonl to markdown, ~/.claude/projects, extract claude sessions, claude code no export button, where are claude code logs stored, claude terminal logs, anthropic claude code export, search claude conversations, find claude code logs location

**Note**: This is an independent tool not affiliated with Anthropic. Use responsibly.