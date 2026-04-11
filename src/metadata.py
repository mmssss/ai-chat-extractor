"""
Session discovery and metadata extraction for Claude JSONL conversation files.

This module handles finding conversation sessions, subagent files,
and extracting metadata from the JSONL format.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .parsers import extract_first_user_text, extract_text_content
except ImportError:
    from parsers import extract_first_user_text, extract_text_content


def find_sessions(
    claude_dir: Path,
    project_path: Optional[str] = None,
    include_subagents: bool = False,
) -> List[Path]:
    """Find all JSONL session files, sorted by most recent first.

    Args:
        claude_dir: Base directory (e.g. ~/.claude/projects)
        project_path: Optional project subdirectory to search in
        include_subagents: If True, include subagent JSONL files in results.
                          If False (default), only return main conversation files.
    """
    if project_path:
        search_dir = claude_dir / project_path
    else:
        search_dir = claude_dir

    sessions = []
    if search_dir.exists():
        for jsonl_file in search_dir.rglob("*.jsonl"):
            if not include_subagents and "/subagents/" in str(jsonl_file):
                continue
            sessions.append(jsonl_file)
    return sorted(sessions, key=lambda x: x.stat().st_mtime, reverse=True)


def find_subagents(session_path: Path) -> List[Path]:
    """Find all subagent JSONL files associated with a main conversation.

    Args:
        session_path: Path to the main conversation JSONL file

    Returns:
        List of paths to subagent JSONL files, sorted by modification time
    """
    session_id = session_path.stem
    session_dir = session_path.parent / session_id
    subagents_dir = session_dir / "subagents"

    if not subagents_dir.exists():
        return []

    subagent_files = sorted(
        [f for f in subagents_dir.glob("agent-*.jsonl")],
        key=lambda x: x.stat().st_mtime,
    )
    return subagent_files


def get_subagent_metadata(subagent_path: Path) -> Dict:
    """Get metadata for a subagent from its .meta.json file and JSONL content.

    Args:
        subagent_path: Path to the subagent JSONL file

    Returns:
        Dict with agent metadata: agentId, agentType, first_message, entry_count, etc.
    """
    meta = {
        "agentId": "",
        "agentType": "unknown",
        "first_message": "",
        "entry_count": 0,
        "first_timestamp": "",
        "last_timestamp": "",
    }

    # Extract agentId from filename: agent-<agentId>.jsonl
    filename = subagent_path.stem  # agent-<agentId>
    if filename.startswith("agent-"):
        meta["agentId"] = filename[6:]

    # Read .meta.json if it exists
    meta_json_path = subagent_path.with_suffix(".meta.json")
    if meta_json_path.exists():
        try:
            with open(meta_json_path, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                meta["agentType"] = meta_data.get("agentType", "unknown")
        except Exception:
            pass

    # Read first user message and timestamps from JSONL
    try:
        with open(subagent_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    meta["entry_count"] += 1

                    ts = entry.get("timestamp", "")
                    if ts and not meta["first_timestamp"]:
                        meta["first_timestamp"] = ts
                    if ts:
                        meta["last_timestamp"] = ts

                    # Get first user message as description
                    if not meta["first_message"] and entry.get("type") == "user":
                        msg = entry.get("message", {})
                        if isinstance(msg, dict):
                            content = msg.get("content", "")
                            text = extract_text_content(content)
                            if text:
                                meta["first_message"] = text[:200]
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return meta


def extract_session_metadata(jsonl_path: Path) -> Dict:
    """Extract all available metadata from a conversation JSONL file.

    Returns dict with: slug, custom_title, first_user_message, sessionId,
    first_timestamp, last_timestamp, models, version, gitBranch, cwd,
    project_path, entry_count, message_count, has_subagents, subagent_count.

    ``entry_count`` counts every JSONL envelope (summaries, custom-title,
    user, assistant, etc.). ``message_count`` counts only user+assistant
    turns — the number a human would recognize as "messages exchanged".
    """
    metadata = {
        "slug": "",
        "custom_title": "",
        "first_user_message": "",
        "sessionId": "",
        "first_timestamp": "",
        "last_timestamp": "",
        "models": set(),
        "version": "",
        "gitBranch": "",
        "cwd": "",
        "project_path": "",
        "entry_count": 0,
        "message_count": 0,
        "has_subagents": False,
        "subagent_count": 0,
        "has_errors": False,
    }

    # Derive project from directory name
    metadata["project_path"] = jsonl_path.parent.name
    metadata["sessionId"] = jsonl_path.stem

    # Check for subagents directory
    session_dir = jsonl_path.parent / jsonl_path.stem
    subagents_dir = session_dir / "subagents"
    if subagents_dir.exists():
        sa_files = list(subagents_dir.glob("agent-*.jsonl"))
        metadata["has_subagents"] = len(sa_files) > 0
        metadata["subagent_count"] = len(sa_files)

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    metadata["entry_count"] += 1

                    # Custom title (user-set via /rename command)
                    if entry.get("type") == "custom-title":
                        title = entry.get("title", "") or entry.get("customTitle", "")
                        if title:
                            metadata["custom_title"] = title

                    # Slug (random internal name)
                    if not metadata["slug"] and entry.get("slug"):
                        metadata["slug"] = entry["slug"]

                    # Timestamps
                    ts = entry.get("timestamp", "")
                    if ts and not metadata["first_timestamp"]:
                        metadata["first_timestamp"] = ts
                    if ts:
                        metadata["last_timestamp"] = ts

                    # Version
                    if not metadata["version"] and entry.get("version"):
                        metadata["version"] = entry["version"]

                    # Git branch
                    if not metadata["gitBranch"] and entry.get("gitBranch"):
                        metadata["gitBranch"] = entry["gitBranch"]

                    # Working directory
                    if not metadata["cwd"] and entry.get("cwd"):
                        metadata["cwd"] = entry["cwd"]

                    # Models used + assistant message count
                    if entry.get("type") == "assistant" and isinstance(
                        entry.get("message"), dict
                    ):
                        model = entry["message"].get("model", "")
                        if model and model != "<synthetic>":
                            metadata["models"].add(model)
                        metadata["message_count"] += 1

                    if entry.get("type") == "user" and isinstance(
                        entry.get("message"), dict
                    ):
                        metadata["message_count"] += 1

                    # Errors
                    if entry.get("error") or entry.get("isApiErrorMessage"):
                        metadata["has_errors"] = True

                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    # Convert set to sorted list for serialization
    metadata["models"] = sorted(metadata["models"])

    # Extract first user message (separate pass for clarity)
    metadata["first_user_message"] = extract_first_user_text(jsonl_path)

    return metadata
