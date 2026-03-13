"""Claude Conversation Extractor - Extract Claude Code conversations to various formats."""

__version__ = "1.1.2"
__author__ = "Dustin Kirby"

from .extract_claude_logs import ClaudeConversationExtractor
from .search_conversations import ConversationSearcher

__all__ = [
    "ClaudeConversationExtractor",
    "ConversationSearcher",
    # Sub-modules for direct access
    "parsers",
    "metadata",
    "formatters",
]
