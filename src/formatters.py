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

try:
    from .metadata import extract_session_metadata, get_subagent_metadata
except ImportError:
    from metadata import extract_session_metadata, get_subagent_metadata


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


def generate_filename(session_path: Path, format: str = "markdown") -> str:
    """Generate output filename from conversation metadata.

    Format: 20260311T081823_claude_<slug>.<ext>

    Priority for slug:
    1. custom_title - user-set name via /rename command
    2. first_user_message - slugified first meaningful user message
    3. session ID prefix - first 8 chars of the UUID

    Args:
        session_path: Path to the JSONL file
        format: Output format ('markdown', 'json', 'html')

    Returns:
        Generated filename string
    """
    ext_map = {"markdown": "md", "json": "json", "html": "html"}
    ext = ext_map.get(format, "md")

    metadata = extract_session_metadata(session_path)

    # Build timestamp part
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

    return f"{ts_part}_claude_{slug_part}.{ext}"


def generate_subagent_filename(
    subagent_path: Path,
    parent_metadata: Dict,
    agent_index: int,
    format: str = "markdown",
) -> str:
    """Generate output filename for a subagent conversation.

    Format: 20260311T081823_claude_<parent-slug>_agent<N>_<agentId-short>.<ext>

    Args:
        subagent_path: Path to the subagent JSONL file
        parent_metadata: Metadata dict from the parent conversation
        agent_index: 1-based index of this agent among siblings
        format: Output format

    Returns:
        Generated filename string
    """
    ext_map = {"markdown": "md", "json": "json", "html": "html"}
    ext = ext_map.get(format, "md")

    # Use parent's timestamp
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

    # Agent ID (short)
    agent_meta = get_subagent_metadata(subagent_path)
    agent_id_short = agent_meta["agentId"][:8] if agent_meta["agentId"] else "unknown"

    return f"{ts_part}_claude_{parent_slug}_agent{agent_index}_{agent_id_short}.{ext}"


def save_as_markdown(
    conversation: List[Dict[str, str]],
    session_id: str,
    output_dir: Path,
    session_path: Optional[Path] = None,
    filename_override: Optional[str] = None,
) -> Optional[Path]:
    """Save conversation as clean markdown file.

    Args:
        conversation: List of message dicts
        session_id: Session identifier (UUID)
        output_dir: Directory to save to
        session_path: Optional path to JSONL file for metadata-based filename
        filename_override: Optional explicit filename to use
    """
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

    if filename_override:
        filename = filename_override
    elif session_path:
        filename = generate_filename(session_path, format="markdown")
    else:
        filename = f"claude-conversation-{date_str}-{session_id[:8]}.md"
    output_path = resolve_output_path(output_dir, filename)
    if output_path is None:
        return None

    role_headers = {
        "user": "## 👤 User\n\n",
        "assistant": "## 🤖 Claude\n\n",
        "tool_use": "### 🔧 Tool Use\n\n",
        "tool_result": "### 📤 Tool Result\n\n",
        "system": "### ℹ️ System\n\n",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Claude Conversation Log\n\n")
        f.write(f"Session ID: {session_id}\n")
        f.write(f"Date: {date_str}")
        if time_str:
            f.write(f" {time_str}")
        f.write("\n\n---\n\n")

        for msg in conversation:
            role = msg["role"]
            content = msg["content"]
            header = role_headers.get(role, f"## {role}\n\n")
            f.write(header)
            f.write(f"{content}\n\n")
            f.write("---\n\n")

    return output_path


def save_as_json(
    conversation: List[Dict[str, str]],
    session_id: str,
    output_dir: Path,
    session_path: Optional[Path] = None,
    filename_override: Optional[str] = None,
) -> Optional[Path]:
    """Save conversation as JSON file.

    Args:
        conversation: List of message dicts
        session_id: Session identifier (UUID)
        output_dir: Directory to save to
        session_path: Optional path to JSONL file for metadata-based filename
        filename_override: Optional explicit filename to use
    """
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

    if filename_override:
        filename = filename_override
    elif session_path:
        filename = generate_filename(session_path, format="json")
    else:
        filename = f"claude-conversation-{date_str}-{session_id[:8]}.json"
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
) -> Optional[Path]:
    """Save conversation as HTML file with syntax highlighting.

    Args:
        conversation: List of message dicts
        session_id: Session identifier (UUID)
        output_dir: Directory to save to
        session_path: Optional path to JSONL file for metadata-based filename
        filename_override: Optional explicit filename to use
    """
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

    if filename_override:
        filename = filename_override
    elif session_path:
        filename = generate_filename(session_path, format="html")
    else:
        filename = f"claude-conversation-{date_str}-{session_id[:8]}.html"
    output_path = resolve_output_path(output_dir, filename)
    if output_path is None:
        return None

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Conversation - {session_id[:8]}</title>
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
        <h1>Claude Conversation Log</h1>
        <div class="metadata">
            <p>Session ID: {session_id}</p>
            <p>Date: {date_str} {time_str}</p>
            <p>Messages: {len(conversation)}</p>
        </div>
    </div>
"""

    role_display = {
        "user": "👤 User",
        "assistant": "🤖 Claude",
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
) -> Optional[Path]:
    """Save conversation in the specified format.

    Args:
        conversation: The conversation data
        session_id: Session identifier
        output_dir: Directory to save to
        format: Output format ('markdown', 'json', 'html')
        session_path: Optional path to JSONL file for metadata-based filename
        filename_override: Optional explicit filename to use
    """
    kwargs = {
        "session_path": session_path,
        "filename_override": filename_override,
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
