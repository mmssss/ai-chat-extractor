"""
Output formatting and file writing for Claude conversations.

This module handles converting parsed conversations into various output
formats (Markdown, JSON, HTML) and generating appropriate filenames.
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .source_adapter import get_source


def _find_min_heading_level(lines):
    """Find the minimum ATX heading level outside code blocks, or None."""
    min_level = None
    in_code_block = False
    for line in lines:
        stripped = line.lstrip()
        if not in_code_block:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_code_block = True
                continue
        else:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_code_block = False
            continue
        m = re.match(r'^(#{1,6})( |$)', line)
        if m:
            level = len(m.group(1))
            if min_level is None or level < min_level:
                min_level = level
    return min_level


def downlevel_headings(text: str, levels: int = None) -> str:
    """Shift markdown headings down to prevent hierarchy collision.

    The exported markdown uses # for the document title and ## for role headers
    (User/Claude). Content headings must be pushed below ## so they don't
    become siblings of — or even override — the document structure.

    When ``levels`` is None (default), the shift is computed adaptively so the
    shallowest content heading becomes h3.  An explicit ``levels`` value
    overrides this and applies a fixed shift instead.

    Only transforms ATX headings outside fenced code blocks.  Caps at h6.
    """
    lines = text.split('\n')

    if levels is None:
        min_level = _find_min_heading_level(lines)
        if min_level is None or min_level >= 3:
            return text  # nothing to shift
        levels = 3 - min_level

    result = []
    in_code_block = False

    for line in lines:
        stripped = line.lstrip()
        # Track fenced code blocks (``` or ~~~, optionally with language tag)
        if not in_code_block:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_code_block = True
                result.append(line)
                continue
        else:
            # Closing fence: must be at least as long as opening, no content after
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_code_block = False
            result.append(line)
            continue

        # ATX heading: 1-6 '#' followed by space or end-of-line
        m = re.match(r'^(#{1,6})( |$)', line)
        if m:
            old_level = len(m.group(1))
            new_level = min(old_level + levels, 6)
            line = '#' * new_level + line[old_level:]

        result.append(line)

    return '\n'.join(result)


def escape_headings(text: str) -> str:
    """Escape markdown heading syntax so '#' renders as literal text.

    Users almost never write intentional markdown headings — a '#' at the
    start of a line is typically a shell comment, pasted code, or a reference
    to a document heading. Escaping with '\\#' preserves the original text
    without creating spurious heading elements in the exported markdown.

    Only escapes ATX heading patterns outside fenced code blocks.
    """
    lines = text.split('\n')
    result = []
    in_code_block = False

    for line in lines:
        stripped = line.lstrip()
        if not in_code_block:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_code_block = True
                result.append(line)
                continue
        else:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_code_block = False
            result.append(line)
            continue

        # Escape ATX heading pattern: 1-6 '#' followed by space or end-of-line
        m = re.match(r'^(#{1,6})( |$)', line)
        if m:
            line = '\\' + line

        result.append(line)

    return '\n'.join(result)


def slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug.

    Examples:
        'glistening-foraging-snail' -> 'glistening-foraging-snail'
        'My Cool Conversation!' -> 'my-cool-conversation'
        'Fix bug in auth/login.py' -> 'fix-bug-in-auth-login-py'
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-]", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    if len(text) > 60:
        text = text[:60].rstrip("-")
    return text


def slug_from_metadata(metadata: Dict) -> str:
    """Derive a filename slug from metadata, with priority chain:

    1. custom_title (user-set via /rename)
    2. first_user_message (content-based)
    3. session ID prefix (fallback)
    """
    if metadata.get("custom_title"):
        return slugify(metadata["custom_title"])
    if metadata.get("first_user_message"):
        return slugify(metadata["first_user_message"])
    return metadata.get("sessionId", "unknown")[:8]


def resolve_output_path(output_dir: Path, filename: str) -> Optional[Path]:
    """Resolve output path, skipping if file already exists.

    Returns:
        Path to write to, or None if the file already exists (skip).
    """
    path = output_dir / filename
    if path.exists():
        return None
    return path


def generate_filename(
    session_path: Path,
    format: str = "markdown",
    source: str = "claude",
) -> str:
    """Generate output filename from conversation metadata.

    Format: 20260311T081823_<prefix>_<slug>.<ext>

    Priority for slug:
    1. custom_title - user-set name
    2. first_user_message - slugified first meaningful user message
    3. session ID prefix - first 8 chars of the UUID
    """
    ext_map = {"markdown": "md", "json": "json", "html": "html"}
    ext = ext_map.get(format, "md")

    adapter = get_source(source)
    metadata = adapter.metadata.extract_session_metadata(session_path)

    first_ts = metadata["first_timestamp"]
    if first_ts:
        try:
            dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            ts_part = dt.strftime("%Y%m%dT%H%M%S")
        except Exception:
            ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")
    else:
        ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")

    slug_part = slug_from_metadata(metadata)

    return f"{ts_part}_{adapter.filename_prefix}_{slug_part}.{ext}"


def generate_subagent_filename(
    subagent_path: Path,
    parent_metadata: Dict,
    agent_index: int,
    format: str = "markdown",
    source: str = "claude",
) -> str:
    """Generate output filename for a subagent conversation.

    Format: 20260311T081823_<prefix>_<parent-slug>_agent<N>_<agent-id>.<ext>
    """
    ext_map = {"markdown": "md", "json": "json", "html": "html"}
    ext = ext_map.get(format, "md")

    first_ts = parent_metadata.get("first_timestamp", "")
    if first_ts:
        try:
            dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            ts_part = dt.strftime("%Y%m%dT%H%M%S")
        except Exception:
            ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")
    else:
        ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")

    parent_slug = slug_from_metadata(parent_metadata)

    adapter = get_source(source)
    agent_meta = adapter.metadata.get_subagent_metadata(subagent_path)
    agent_part = agent_meta.get(
        "agent_id_display",
        agent_meta["agentId"][:8] if agent_meta["agentId"] else "unknown",
    )

    return (
        f"{ts_part}_{adapter.filename_prefix}_{parent_slug}"
        f"_agent{agent_index}_{agent_part}.{ext}"
    )


def save_as_markdown(
    conversation: List[Dict[str, str]],
    session_id: str,
    output_dir: Path,
    session_path: Optional[Path] = None,
    filename_override: Optional[str] = None,
    source: str = "claude",
) -> Optional[Path]:
    """Save conversation as clean markdown file."""
    if not conversation:
        return None

    first_timestamp = conversation[0].get("timestamp", "")
    if first_timestamp:
        try:
            dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = ""
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = ""

    adapter = get_source(source)
    if filename_override:
        filename = filename_override
    elif session_path:
        filename = generate_filename(session_path, format="markdown", source=source)
    else:
        filename = (
            f"{adapter.filename_prefix}-conversation-{date_str}-{session_id[:8]}.md"
        )
    output_path = resolve_output_path(output_dir, filename)
    if output_path is None:
        return None

    role_headers = {
        "user": "## 👤 User\n\n",
        "assistant": f"## 🤖 {adapter.display_name}\n\n",
        "tool_use": "### 🔧 Tool Use\n\n",
        "tool_result": "### 📤 Tool Result\n\n",
        "system": "### ℹ️ System\n\n",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {adapter.display_name} Conversation Log\n\n")
        f.write(f"Session ID: {session_id}\n")
        f.write(f"Date: {date_str}")
        if time_str:
            f.write(f" {time_str}")
        f.write("\n\n")

        for msg in conversation:
            role = msg["role"]
            content = msg["content"].strip()
            header = role_headers.get(role, f"## {role}\n\n")
            f.write(header)
            if role == "user":
                f.write(f"{escape_headings(content)}\n\n")
            else:
                f.write(f"{downlevel_headings(content)}\n\n")

    return output_path


def save_as_json(
    conversation: List[Dict[str, str]],
    session_id: str,
    output_dir: Path,
    session_path: Optional[Path] = None,
    filename_override: Optional[str] = None,
    source: str = "claude",
) -> Optional[Path]:
    """Save conversation as JSON file."""
    if not conversation:
        return None

    first_timestamp = conversation[0].get("timestamp", "")
    if first_timestamp:
        try:
            dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    adapter = get_source(source)
    if filename_override:
        filename = filename_override
    elif session_path:
        filename = generate_filename(session_path, format="json", source=source)
    else:
        filename = (
            f"{adapter.filename_prefix}-conversation-{date_str}-{session_id[:8]}.json"
        )
    output_path = resolve_output_path(output_dir, filename)
    if output_path is None:
        return None

    output = {
        "session_id": session_id,
        "date": date_str,
        "message_count": len(conversation),
        "messages": conversation,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output_path


def save_as_html(
    conversation: List[Dict[str, str]],
    session_id: str,
    output_dir: Path,
    session_path: Optional[Path] = None,
    filename_override: Optional[str] = None,
    source: str = "claude",
) -> Optional[Path]:
    """Save conversation as HTML file with syntax highlighting."""
    if not conversation:
        return None

    first_timestamp = conversation[0].get("timestamp", "")
    if first_timestamp:
        try:
            dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = ""
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = ""

    adapter = get_source(source)
    if filename_override:
        filename = filename_override
    elif session_path:
        filename = generate_filename(session_path, format="html", source=source)
    else:
        filename = (
            f"{adapter.filename_prefix}-conversation-{date_str}-{session_id[:8]}.html"
        )
    output_path = resolve_output_path(output_dir, filename)
    if output_path is None:
        return None

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{adapter.display_name} Conversation - {session_id[:8]}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            margin: 0 0 10px 0;
        }}
        .metadata {{
            color: #666;
            font-size: 0.9em;
        }}
        .message {{
            background: white;
            padding: 15px 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .user {{
            border-left: 4px solid #3498db;
        }}
        .assistant {{
            border-left: 4px solid #2ecc71;
        }}
        .tool_use {{
            border-left: 4px solid #f39c12;
            background: #fffbf0;
        }}
        .tool_result {{
            border-left: 4px solid #e74c3c;
            background: #fff5f5;
        }}
        .system {{
            border-left: 4px solid #95a5a6;
            background: #f8f9fa;
        }}
        .role {{
            font-weight: bold;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
        }}
        .content {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        pre {{
            background: #f4f4f4;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{adapter.display_name} Conversation Log</h1>
        <div class="metadata">
            <p>Session ID: {session_id}</p>
            <p>Date: {date_str} {time_str}</p>
            <p>Messages: {len(conversation)}</p>
        </div>
    </div>
"""

    role_display = {
        "user": "👤 User",
        "assistant": f"🤖 {adapter.display_name}",
        "tool_use": "🔧 Tool Use",
        "tool_result": "📤 Tool Result",
        "system": "ℹ️ System",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

        for msg in conversation:
            role = msg["role"]
            content = msg["content"]

            # Escape HTML
            content = content.replace("&", "&amp;")
            content = content.replace("<", "&lt;")
            content = content.replace(">", "&gt;")

            display = role_display.get(role, role)

            f.write(f'    <div class="message {role}">\n')
            f.write(f'        <div class="role">{display}</div>\n')
            f.write(f'        <div class="content">{content}</div>\n')
            f.write('    </div>\n')

        f.write("\n</body>\n</html>")

    return output_path


def save_conversation(
    conversation: List[Dict[str, str]],
    session_id: str,
    output_dir: Path,
    format: str = "markdown",
    session_path: Optional[Path] = None,
    filename_override: Optional[str] = None,
    source: str = "claude",
) -> Optional[Path]:
    """Save conversation in the specified format."""
    kwargs = {
        "session_path": session_path,
        "filename_override": filename_override,
        "source": source,
    }
    if format == "markdown":
        return save_as_markdown(conversation, session_id, output_dir, **kwargs)
    elif format == "json":
        return save_as_json(conversation, session_id, output_dir, **kwargs)
    elif format == "html":
        return save_as_html(conversation, session_id, output_dir, **kwargs)
    else:
        print(f"❌ Unsupported format: {format}")
        return None
