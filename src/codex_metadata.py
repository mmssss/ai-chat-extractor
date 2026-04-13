"""
Session discovery and metadata extraction for OpenAI Codex rollout files.

Mirrors the public surface of metadata.py so ConversationExtractor can
dispatch through a SourceAdapter without branching on source name.
"""

import functools
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .codex_parsers import extract_first_user_text
except ImportError:
    from codex_parsers import extract_first_user_text


SESSION_INDEX_PATH = Path.home() / ".codex" / "session_index.jsonl"


def find_sessions(
    codex_dir: Path,
    project_path: Optional[str] = None,
    include_subagents: bool = False,
) -> List[Path]:
    """Find all Codex rollout files, sorted by most recent first.

    Codex stores sessions under ``~/.codex/sessions/YYYY/MM/DD/`` with a
    flat ``rollout-*.jsonl`` per session. Subagents are sibling files
    inside the parent's date directory — distinguished only by peeking
    line 0 for ``payload.source.subagent``.
    """
    search_dir = codex_dir / project_path if project_path else codex_dir
    sessions: List[Path] = []
    if not search_dir.exists():
        return sessions

    for rollout in search_dir.rglob("rollout-*.jsonl"):
        if not include_subagents and _is_subagent_file(rollout):
            continue
        sessions.append(rollout)

    return sorted(sessions, key=lambda x: x.stat().st_mtime, reverse=True)


def _is_subagent_file(jsonl_path: Path) -> bool:
    """Peek line 0 and return True if the session_meta marks this as a subagent."""
    meta = _read_session_meta(jsonl_path)
    if not meta:
        return False
    source_field = meta.get("source")
    if isinstance(source_field, dict) and "subagent" in source_field:
        return True
    return False


def _read_session_meta(jsonl_path: Path) -> Optional[Dict]:
    """Return the ``payload`` of the first-line session_meta envelope, or None."""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
        entry = json.loads(first_line)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(entry, dict):
        return None
    if entry.get("type") != "session_meta":
        return None
    payload = entry.get("payload")
    return payload if isinstance(payload, dict) else None


def find_subagents(session_path: Path) -> List[Path]:
    """Find sibling rollout files whose session_meta points at this session.

    Scans the parent's date directory and the next UTC day's directory so
    a subagent that spawned just before midnight still gets picked up even
    if its rollout file lands in tomorrow's folder.
    """
    parent_meta = _read_session_meta(session_path)
    if not parent_meta:
        return []
    parent_id = parent_meta.get("id", "")
    if not parent_id:
        return []

    subagents: List[Path] = []
    for candidate in _subagent_search_dirs(session_path):
        for sibling in candidate.glob("rollout-*.jsonl"):
            if sibling == session_path:
                continue
            sibling_meta = _read_session_meta(sibling)
            if not sibling_meta:
                continue
            source_field = sibling_meta.get("source")
            if not isinstance(source_field, dict):
                continue
            subagent_info = source_field.get("subagent")
            if not isinstance(subagent_info, dict):
                continue
            thread_spawn = subagent_info.get("thread_spawn") or {}
            if thread_spawn.get("parent_thread_id") == parent_id:
                subagents.append(sibling)

    return sorted(subagents, key=lambda x: x.stat().st_mtime)


def _subagent_search_dirs(session_path: Path) -> List[Path]:
    """Return [parent_dir, next_day_dir] when the parent path is a YYYY/MM/DD tree.

    Codex rollouts live at ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``.
    A subagent spawned at 23:59 UTC may land in tomorrow's directory, so we
    also probe ``YYYY/MM/(DD+1)`` — computed via ``datetime.date`` so month
    and year rollovers are handled correctly.
    """
    dirs: List[Path] = [session_path.parent]
    try:
        day = int(session_path.parent.name)
        month = int(session_path.parent.parent.name)
        year = int(session_path.parent.parent.parent.name)
        next_day = date(year, month, day) + timedelta(days=1)
    except (ValueError, AttributeError):
        return dirs
    next_dir = (
        session_path.parent.parent.parent.parent
        / f"{next_day.year:04d}"
        / f"{next_day.month:02d}"
        / f"{next_day.day:02d}"
    )
    if next_dir.exists() and next_dir != session_path.parent:
        dirs.append(next_dir)
    return dirs


def get_subagent_metadata(subagent_path: Path) -> Dict:
    """Return subagent metadata — mirrors Claude's shape plus Codex extras.

    The ``agent_id_display`` key carries the pre-formatted identifier
    used by ``formatters.generate_subagent_filename``: ``nickname_shortUUID``
    when a nickname is present, else ``shortUUID`` alone.
    """
    meta: Dict = {
        "agentId": "",
        "agentType": "unknown",
        "agent_nickname": "",
        "agent_id_display": "unknown",
        "first_message": "",
        "entry_count": 0,
        "first_timestamp": "",
        "last_timestamp": "",
    }

    session_meta = _read_session_meta(subagent_path)
    if session_meta:
        agent_id = session_meta.get("id", "") or ""
        meta["agentId"] = agent_id
        source_field = session_meta.get("source") or {}
        thread_spawn = {}
        if isinstance(source_field, dict):
            subagent_info = source_field.get("subagent") or {}
            if isinstance(subagent_info, dict):
                thread_spawn = subagent_info.get("thread_spawn") or {}
        nickname = (
            thread_spawn.get("agent_nickname")
            or session_meta.get("agent_nickname")
            or ""
        )
        role = (
            thread_spawn.get("agent_role")
            or session_meta.get("agent_role")
            or "unknown"
        )
        meta["agentType"] = role
        meta["agent_nickname"] = nickname
        agent_id_short = agent_id[:8] if agent_id else "unknown"
        if nickname:
            meta["agent_id_display"] = f"{nickname}_{agent_id_short}"
        else:
            meta["agent_id_display"] = agent_id_short

    try:
        with open(subagent_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                meta["entry_count"] += 1
                ts = entry.get("timestamp", "")
                if ts and not meta["first_timestamp"]:
                    meta["first_timestamp"] = ts
                if ts:
                    meta["last_timestamp"] = ts

                if not meta["first_message"]:
                    payload = entry.get("payload") or {}
                    if (
                        entry.get("type") == "event_msg"
                        and isinstance(payload, dict)
                        and payload.get("type") == "user_message"
                    ):
                        text = payload.get("message", "")
                        if isinstance(text, str) and text.strip():
                            meta["first_message"] = text.strip()[:200]
    except Exception:
        pass

    return meta


def project_label(session: Path, session_meta: Dict) -> str:
    """Return a human-friendly project label for the listing display.

    Codex rollouts live under ``YYYY/MM/DD/`` so the parent dir name is a
    date — the real project identity comes from ``session_meta.cwd``.
    """
    cwd = session_meta.get("cwd", "") or ""
    if not cwd:
        return session.parent.name
    home = str(Path.home())
    if cwd.startswith(home):
        return "~" + cwd[len(home):]
    return cwd


def extract_session_metadata(jsonl_path: Path) -> Dict:
    """Return a metadata dict with the same keys formatters/list UI expect.

    Populated from the ``session_meta`` envelope on line 0, one forward
    pass over the file for timestamps/counts, and a lookup in
    ``~/.codex/session_index.jsonl`` for the thread name (Codex's
    equivalent of Claude's ``custom-title``).
    """
    meta: Dict = {
        "slug": "",
        "custom_title": "",
        "first_user_message": "",
        "sessionId": "",
        "first_timestamp": "",
        "last_timestamp": "",
        "models": [],
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

    meta["project_path"] = jsonl_path.parent.name
    meta["sessionId"] = jsonl_path.stem.replace("rollout-", "")

    session_meta = _read_session_meta(jsonl_path)
    session_model: str = ""
    if session_meta:
        sid = session_meta.get("id", "")
        if sid:
            meta["sessionId"] = sid
        meta["cwd"] = session_meta.get("cwd", "") or ""
        meta["version"] = session_meta.get("cli_version", "") or ""
        meta["first_timestamp"] = session_meta.get("timestamp", "") or ""
        session_model = session_meta.get("model") or ""

        thread_name = _read_session_index().get(sid, "")
        if thread_name:
            meta["custom_title"] = thread_name

    models_seen: set = set()
    if session_model:
        models_seen.add(session_model)
    last_ts = meta["first_timestamp"]
    has_errors = False
    entry_count = 0
    message_count = 0

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_count += 1
                ts = entry.get("timestamp", "")
                if ts:
                    last_ts = ts

                etype = entry.get("type")
                payload = entry.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                ptype = payload.get("type")

                if etype == "turn_context":
                    tc_model = payload.get("model")
                    if isinstance(tc_model, str) and tc_model:
                        models_seen.add(tc_model)

                if etype == "event_msg" and ptype == "error":
                    has_errors = True

                if etype == "event_msg" and ptype == "user_message":
                    message_count += 1
                elif (
                    etype == "response_item"
                    and ptype == "message"
                    and payload.get("role") == "assistant"
                ):
                    message_count += 1
    except Exception:
        pass

    meta["entry_count"] = entry_count
    meta["message_count"] = message_count
    meta["last_timestamp"] = last_ts
    meta["has_errors"] = has_errors
    meta["models"] = sorted(models_seen)

    meta["first_user_message"] = extract_first_user_text(jsonl_path)

    subagents = find_subagents(jsonl_path)
    if subagents:
        meta["has_subagents"] = True
        meta["subagent_count"] = len(subagents)

    return meta


@functools.lru_cache(maxsize=1)
def _read_session_index() -> Dict[str, str]:
    """Return ``{session_uuid: thread_name}`` from ~/.codex/session_index.jsonl.

    Last-write-wins: later entries in the file override earlier ones for
    the same UUID. The result is cached for the lifetime of the process
    since the index is small (~dozens of entries) and rarely edited.
    """
    mapping: Dict[str, str] = {}
    if not SESSION_INDEX_PATH.exists():
        return mapping
    try:
        with open(SESSION_INDEX_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = entry.get("id", "")
                name = entry.get("thread_name", "")
                if sid and name:
                    mapping[sid] = name
    except OSError:
        pass
    return mapping
