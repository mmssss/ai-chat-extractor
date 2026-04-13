"""
Content parsing and text extraction for Claude JSONL conversation files.

This module contains pure functions for parsing the undocumented JSONL format
used by Claude Code to store conversations in ~/.claude/projects/.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def is_ide_preamble(text: str) -> bool:
    """Check if text is an IDE-generated preamble rather than real user input."""
    preamble_patterns = [
        "The user opened the file",
        "The user selected the lines",
        "The user is currently viewing",
        "The user has the following",
        "Caveat: The messages below",
    ]
    return any(text.startswith(p) for p in preamble_patterns)


def _clean_slash_command(text: str) -> str:
    """Clean up slash command text that gets duplicated by IDE.

    The IDE sometimes produces: '/command             command             args'
    This cleans it to: '/command args'

    Also handles non-slash duplicates: 'extra-usage             extra-usage'
    """
    # Slash command with duplicate: /word<whitespace>word<whitespace>rest
    match = re.match(r'^/(\S+)\s+\1(?:\s+(.*))?$', text, re.DOTALL)
    if match:
        rest = (match.group(2) or "").strip()
        return f"/{match.group(1)} {rest}".strip() if rest else f"/{match.group(1)}"
    # Non-slash duplicate: word<whitespace>word
    match = re.match(r'^(\S+)\s+\1(?:\s+(.*))?$', text, re.DOTALL)
    if match:
        rest = (match.group(2) or "").strip()
        return f"{match.group(1)} {rest}".strip() if rest else match.group(1)
    return text


def extract_text_content(content, detailed: bool = False) -> str:
    """Extract text from various content formats Claude uses.

    Args:
        content: The content to extract from (str, list, or other)
        detailed: If True, include tool use blocks and other metadata
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif detailed and item.get("type") == "tool_use":
                    tool_name = item.get("name", "unknown")
                    tool_input = item.get("input", {})
                    text_parts.append(f"\n🔧 Using tool: {tool_name}")
                    text_parts.append(f"Input: {json.dumps(tool_input, indent=2)}\n")
        return "\n".join(text_parts)
    else:
        return str(content)


def extract_first_user_text(jsonl_path: Path) -> str:
    """Extract the first meaningful user message text from a JSONL file.

    Skips meta messages, IDE preambles, tool results, interruptions,
    and system continuations. Returns empty string if no meaningful
    message found.
    """
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("type") != "user" or "message" not in data:
                        continue
                    # Skip meta entries (local commands, etc.)
                    if data.get("isMeta"):
                        continue
                    msg = data["message"]
                    if not isinstance(msg, dict) or msg.get("role") != "user":
                        continue
                    content = msg.get("content", "")

                    if isinstance(content, list):
                        for item in content:
                            if not isinstance(item, dict) or item.get("type") != "text":
                                continue
                            text = item.get("text", "").strip()
                            if text.startswith("tool_use_id"):
                                continue
                            if "[Request interrupted" in text:
                                continue
                            if "session is being continued" in text.lower():
                                continue
                            text = re.sub(r'<[^>]+>', '', text).strip()
                            text = re.sub(r'\x1b\[[0-9;]*m', '', text).strip()
                            if "is running" in text and "\u2026" in text:
                                continue
                            if is_ide_preamble(text):
                                continue
                            text = _clean_slash_command(text)
                            if re.match(r'^/\w+$', text):
                                continue
                            if text and len(text) > 3:
                                return text[:100].replace('\n', ' ').strip()
                    elif isinstance(content, str):
                        text = content.strip()
                        text = re.sub(r'<[^>]+>', '', text).strip()
                        text = re.sub(r'\x1b\[[0-9;]*m', '', text).strip()
                        if "is running" in text and "\u2026" in text:
                            continue
                        if "session is being continued" in text.lower():
                            continue
                        if is_ide_preamble(text):
                            continue
                        text = _clean_slash_command(text)
                        if re.match(r'^/\w+$', text):
                            continue
                        not_tool = not text.startswith("tool_use_id")
                        not_interrupted = "[Request interrupted" not in text
                        if not_tool and not_interrupted:
                            if text and len(text) > 3:
                                return text[:100].replace('\n', ' ').strip()
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return ""


def extract_conversation(jsonl_path: Path, detailed: bool = False) -> List[Dict[str, str]]:
    """Extract conversation messages from a JSONL file.

    Args:
        jsonl_path: Path to the JSONL file
        detailed: If True, include tool use, MCP responses, and system messages
    """
    conversation = []

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())

                    # Extract user messages
                    if entry.get("type") == "user" and "message" in entry:
                        msg = entry["message"]
                        if isinstance(msg, dict) and msg.get("role") == "user":
                            content = msg.get("content", "")
                            text = extract_text_content(content)

                            if text and text.strip():
                                conversation.append(
                                    {
                                        "role": "user",
                                        "content": text,
                                        "timestamp": entry.get("timestamp", ""),
                                    }
                                )

                    # Extract assistant messages
                    elif entry.get("type") == "assistant" and "message" in entry:
                        msg = entry["message"]
                        if isinstance(msg, dict) and msg.get("role") == "assistant":
                            content = msg.get("content", [])
                            text = extract_text_content(content, detailed=detailed)

                            if text and text.strip():
                                conversation.append(
                                    {
                                        "role": "assistant",
                                        "content": text,
                                        "timestamp": entry.get("timestamp", ""),
                                    }
                                )

                    # Include tool use and system messages if detailed mode
                    elif detailed:
                        if entry.get("type") == "tool_use":
                            tool_data = entry.get("tool", {})
                            tool_name = tool_data.get("name", "unknown")
                            tool_input = tool_data.get("input", {})
                            conversation.append(
                                {
                                    "role": "tool_use",
                                    "content": (
                                        f"🔧 Tool: {tool_name}\n"
                                        f"Input: {json.dumps(tool_input, indent=2)}"
                                    ),
                                    "timestamp": entry.get("timestamp", ""),
                                }
                            )

                        elif entry.get("type") == "tool_result":
                            result = entry.get("result", {})
                            output = result.get("output", "") or result.get("error", "")
                            conversation.append(
                                {
                                    "role": "tool_result",
                                    "content": f"📤 Result:\n{output}",
                                    "timestamp": entry.get("timestamp", ""),
                                }
                            )

                        elif entry.get("type") == "system" and "message" in entry:
                            msg = entry.get("message", "")
                            if msg:
                                conversation.append(
                                    {
                                        "role": "system",
                                        "content": f"ℹ️ System: {msg}",
                                        "timestamp": entry.get("timestamp", ""),
                                    }
                                )

                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue

    except Exception as e:
        print(f"❌ Error reading file {jsonl_path}: {e}")

    return conversation


def get_conversation_preview(session_path: Path) -> Tuple[str, int]:
    """Get a preview of the conversation's first real user message and message count."""
    try:
        first_user_msg = ""
        msg_count = 0

        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                msg_count += 1
                if not first_user_msg:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "user" and "message" in data:
                            msg = data["message"]
                            if msg.get("role") == "user":
                                content = msg.get("content", "")

                                if isinstance(content, list):
                                    for item in content:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            text = item.get("text", "").strip()
                                            if text.startswith("tool_use_id"):
                                                continue
                                            if "[Request interrupted" in text:
                                                continue
                                            if "session is being continued" in text.lower():
                                                continue
                                            text = re.sub(r'<[^>]+>', '', text).strip()
                                            if "is running" in text and "\u2026" in text:
                                                continue
                                            if text.startswith("[Image #"):
                                                parts = text.split("]", 1)
                                                if len(parts) > 1:
                                                    text = parts[1].strip()
                                            if text and len(text) > 3:
                                                first_user_msg = text[:100].replace('\n', ' ')
                                                break

                                elif isinstance(content, str):
                                    content = content.strip()
                                    content = re.sub(r'<[^>]+>', '', content).strip()
                                    if "is running" in content and "\u2026" in content:
                                        continue
                                    if "session is being continued" in content.lower():
                                        continue
                                    if (
                                        not content.startswith("tool_use_id")
                                        and "[Request interrupted" not in content
                                    ):
                                        if content and len(content) > 3:
                                            first_user_msg = content[:100].replace('\n', ' ')
                    except json.JSONDecodeError:
                        continue

        return first_user_msg or "No preview available", msg_count
    except Exception as e:
        return f"Error: {str(e)[:30]}", 0


def extract_search_content(entry: Any) -> Optional[Tuple[str, str]]:
    """Extract ``(text, speaker)`` for search indexing, or ``None`` to skip.

    Mirrors ``codex_parsers.extract_search_content`` so ConversationSearcher
    can dispatch through the adapter without branching on source.
    """
    if not isinstance(entry, dict):
        return None

    etype = entry.get("type")
    if etype not in ("user", "assistant"):
        return None

    message = entry.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        text = " ".join(p for p in parts if p).strip()
    elif isinstance(content, str):
        text = content.strip()
    else:
        return None

    if not text:
        return None

    speaker = "human" if etype == "user" else "assistant"
    return text, speaker
