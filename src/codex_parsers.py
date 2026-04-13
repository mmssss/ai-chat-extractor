"""
Content parsing and text extraction for OpenAI Codex JSONL conversation files.

Codex rollout files live under ~/.codex/sessions/YYYY/MM/DD/ and use an
envelope-per-line format: {timestamp, type, payload}. This module mirrors
the signatures in parsers.py so both sources can be dispatched uniformly
through the SourceAdapter registry.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Markers that indicate a response_item user-role message carries the
# AGENTS.md / permissions injection rather than a real user turn.
_INJECTION_MARKERS = (
    "<permissions",
    "<collaboration_mode",
    "<user_instructions",
    "AGENTS.md",
)

_DEVELOPER_TRUNCATE = 2000


def is_ide_preamble(text: str) -> bool:
    """Codex has no IDE-generated preamble concept; always False."""
    return False


def extract_text_content(content, detailed: bool = False) -> str:
    """Extract text from Codex content shapes.

    Codex message content is a list of dicts with ``type`` in
    {``input_text``, ``output_text``, ``summary_text``}. A few event_msg
    payloads use plain strings.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")
            if item_type in ("input_text", "output_text", "summary_text", "text"):
                parts.append(item.get("text", ""))
        return "\n".join(p for p in parts if p)
    return str(content) if content is not None else ""


def _looks_like_injection(text: str) -> bool:
    """Detect AGENTS.md / permissions injection blocks inside user content."""
    snippet = text.lstrip()[:200]
    return any(marker in snippet for marker in _INJECTION_MARKERS)


def extract_first_user_text(jsonl_path: Path) -> str:
    """Return the first meaningful user message text from a Codex rollout.

    Only considers ``event_msg.user_message`` envelopes — the
    ``response_item.message`` with ``role=user`` variant carries the
    AGENTS.md / <permissions> injection and would produce noise.
    """
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "event_msg":
                    continue
                payload = entry.get("payload") or {}
                if payload.get("type") != "user_message":
                    continue
                message = payload.get("message", "")
                if not isinstance(message, str):
                    continue
                text = message.strip()
                if not text or _looks_like_injection(text):
                    continue
                text = re.sub(r"\s+", " ", text)
                return text[:100].strip()
    except Exception:
        pass
    return ""


def _concat_message_content(content, detailed: bool = False) -> str:
    """Concatenate a Codex ``payload.content`` list into a single string."""
    return extract_text_content(content, detailed=detailed).strip()


def _format_tool_input(raw_input: Any) -> str:
    """Render a tool-call input field as a human-readable string.

    Strings that already contain newlines are passed through unchanged —
    they're either pre-formatted or intentionally multi-line, and a second
    json.loads/json.dumps round-trip is wasted work on multi-KB payloads.
    Only compact single-line JSON strings get pretty-printed.
    """
    if isinstance(raw_input, str):
        if not raw_input:
            return ""
        if "\n" in raw_input:
            return raw_input
        try:
            return json.dumps(json.loads(raw_input), indent=2)
        except (json.JSONDecodeError, ValueError):
            return raw_input
    return json.dumps(raw_input, indent=2, default=str)


def extract_conversation(
    jsonl_path: Path, detailed: bool = False
) -> List[Dict[str, str]]:
    """Walk a Codex rollout file and build a list of message dicts.

    Walker rules (see plan):
      1. ``event_msg.user_message`` → role=user
      2. ``response_item.message`` role=assistant → role=assistant
      3. ``response_item.message`` role=developer → system in detailed mode
      4. ``response_item.reasoning`` → always skipped (encrypted_content)
      5. ``response_item.function_call`` / ``local_shell_call``
         / ``custom_tool_call`` → tool_use in detailed mode
      6. ``response_item.function_call_output``
         / ``custom_tool_call_output`` → tool_result in detailed mode
      7. ``response_item.web_search_call`` → tool_use in detailed mode
      8. ``compacted`` → system ``[compaction] ...`` in detailed mode
      9. Any other ``response_item.<ptype>`` in detailed mode surfaces as
         ``[skipped: type=<ptype>]`` so the user knows something was
         emitted but isn't yet walked in full.
    """
    conversation: List[Dict[str, str]] = []

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type")
                payload = entry.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                timestamp = entry.get("timestamp", "")
                ptype = payload.get("type")

                if etype == "event_msg" and ptype == "user_message":
                    text = payload.get("message", "")
                    if isinstance(text, str) and text.strip():
                        conversation.append({
                            "role": "user",
                            "content": text.strip(),
                            "timestamp": timestamp,
                        })
                    continue

                if etype == "response_item" and ptype == "message":
                    role = payload.get("role")
                    content = payload.get("content", [])
                    if role == "assistant":
                        text = _concat_message_content(content, detailed=detailed)
                        if text:
                            conversation.append({
                                "role": "assistant",
                                "content": text,
                                "timestamp": timestamp,
                            })
                    elif role == "developer" and detailed:
                        text = _concat_message_content(content)
                        if text:
                            if len(text) > _DEVELOPER_TRUNCATE:
                                text = text[:_DEVELOPER_TRUNCATE] + " …[truncated]"
                            conversation.append({
                                "role": "system",
                                "content": f"[developer] {text}",
                                "timestamp": timestamp,
                            })
                    continue

                if etype == "response_item" and ptype == "reasoning":
                    continue

                if detailed and etype == "response_item" and ptype in (
                    "function_call", "local_shell_call", "custom_tool_call"
                ):
                    name = payload.get("name", "unknown")
                    raw_input = (
                        payload.get("arguments")
                        or payload.get("input")
                        or payload.get("action")
                        or ""
                    )
                    pretty = _format_tool_input(raw_input)
                    conversation.append({
                        "role": "tool_use",
                        "content": f"🔧 Tool: {name}\nInput: {pretty}",
                        "timestamp": timestamp,
                    })
                    continue

                if detailed and etype == "response_item" and ptype in (
                    "function_call_output", "custom_tool_call_output"
                ):
                    output = payload.get("output", "")
                    if isinstance(output, (dict, list)):
                        output = json.dumps(output, indent=2, default=str)
                    conversation.append({
                        "role": "tool_result",
                        "content": f"📤 Result:\n{output}",
                        "timestamp": timestamp,
                    })
                    continue

                if detailed and etype == "response_item" and ptype == "web_search_call":
                    action = payload.get("action") or {}
                    if isinstance(action, dict):
                        query = action.get("query") or action.get("queries") or ""
                    else:
                        query = ""
                    pretty = _format_tool_input(query)
                    conversation.append({
                        "role": "tool_use",
                        "content": f"🔧 Tool: web_search\nInput: {pretty}",
                        "timestamp": timestamp,
                    })
                    continue

                if detailed and etype == "compacted":
                    message = payload.get("message", "")
                    if isinstance(message, str) and message.strip():
                        conversation.append({
                            "role": "system",
                            "content": f"[compaction] {message.strip()}",
                            "timestamp": timestamp,
                        })
                    continue

                if detailed and etype == "response_item":
                    # Catch-all: visible in --detailed so the user knows
                    # something was emitted but isn't yet walked in full.
                    conversation.append({
                        "role": "system",
                        "content": f"[skipped: type={ptype}]",
                        "timestamp": timestamp,
                    })
                    continue

    except Exception as e:
        print(f"❌ Error reading file {jsonl_path}: {e}")

    return conversation


def get_conversation_preview(session_path: Path) -> Tuple[str, int]:
    """Return ``(first_user_preview, message_count)`` for a Codex rollout.

    ``message_count`` counts user + assistant turns (not every envelope).
    """
    preview = ""
    msg_count = 0
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type")
                payload = entry.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                ptype = payload.get("type")

                if etype == "event_msg" and ptype == "user_message":
                    text = payload.get("message", "")
                    if isinstance(text, str) and text.strip():
                        msg_count += 1
                        if not preview and not _looks_like_injection(text):
                            preview = re.sub(r"\s+", " ", text).strip()[:100]
                    continue

                if etype == "response_item" and ptype == "message":
                    if payload.get("role") == "assistant":
                        msg_count += 1
    except Exception as e:
        return f"Error: {str(e)[:30]}", 0

    return preview or "No preview available", msg_count


def extract_search_content(entry: Any) -> Optional[Tuple[str, str]]:
    """Extract ``(text, speaker)`` for search indexing, or ``None`` to skip.

    Only real user turns and assistant messages are indexed. AGENTS.md
    injection, reasoning, tool calls, and event_msg mirrors are skipped so
    search hits land on substantive conversation content.
    """
    if not isinstance(entry, dict):
        return None

    etype = entry.get("type")
    payload = entry.get("payload") or {}
    if not isinstance(payload, dict):
        return None
    ptype = payload.get("type")

    if etype == "event_msg" and ptype == "user_message":
        text = payload.get("message", "")
        if isinstance(text, str) and text.strip() and not _looks_like_injection(text):
            return text.strip(), "human"
        return None

    if etype == "response_item" and ptype == "message":
        role = payload.get("role")
        if role == "assistant":
            text = _concat_message_content(payload.get("content", []))
            if text:
                return text, "assistant"
        return None

    return None
