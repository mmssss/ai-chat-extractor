#!/usr/bin/env python3
"""
Synthetic Codex rollout files for exercising codex_parsers, codex_metadata,
and the ConversationExtractor's Codex path.

The builder helpers below emit the envelope-per-line shape Codex actually
uses ({timestamp, type, payload}) so the fixtures are walker-faithful:
tests that run the real codex_parsers.extract_conversation against these
files are verifying the same code paths that run against ~/.codex/sessions/.
"""

import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


# ── Envelope builders ──────────────────────────────────────────────────

def _envelope(ts: str, etype: str, payload: Dict) -> Dict:
    return {"timestamp": ts, "type": etype, "payload": payload}


def session_meta(
    session_id: str,
    ts: str,
    cwd: str = "/home/test/project",
    cli_version: str = "0.20.0",
    model: str = "gpt-5-codex",
    model_provider: str = "openai",
    subagent_parent_id: Optional[str] = None,
    agent_nickname: Optional[str] = None,
    agent_role: Optional[str] = None,
) -> Dict:
    """Build a line-0 session_meta envelope.

    When ``subagent_parent_id`` is set, the payload carries the
    ``source.subagent.thread_spawn`` linkage that ``_is_subagent_file``
    and ``find_subagents`` look for.
    """
    payload: Dict = {
        "id": session_id,
        "cwd": cwd,
        "cli_version": cli_version,
        "timestamp": ts,
        "model": model,
        "model_provider": model_provider,
    }
    if subagent_parent_id:
        thread_spawn: Dict = {"parent_thread_id": subagent_parent_id}
        if agent_nickname:
            thread_spawn["agent_nickname"] = agent_nickname
        if agent_role:
            thread_spawn["agent_role"] = agent_role
        payload["source"] = {"subagent": {"thread_spawn": thread_spawn}}
    return _envelope(ts, "session_meta", payload)


def turn_context(ts: str, model: str = "gpt-5-codex") -> Dict:
    return _envelope(ts, "turn_context", {"model": model})


def user_message(ts: str, text: str) -> Dict:
    return _envelope(
        ts, "event_msg", {"type": "user_message", "message": text}
    )


def assistant_message(ts: str, text: str) -> Dict:
    return _envelope(
        ts,
        "response_item",
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    )


def developer_message(ts: str, text: str) -> Dict:
    return _envelope(
        ts,
        "response_item",
        {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": text}],
        },
    )


def user_role_injection(ts: str, text: str) -> Dict:
    """A response_item with role=user that carries AGENTS.md injection.

    The walker must skip these in favor of the event_msg.user_message mirror.
    """
    return _envelope(
        ts,
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    )


def reasoning_item(ts: str, encrypted: str = "<opaque>") -> Dict:
    return _envelope(
        ts,
        "response_item",
        {
            "type": "reasoning",
            "encrypted_content": encrypted,
            "summary": [],
        },
    )


def function_call(ts: str, name: str, arguments: Dict) -> Dict:
    return _envelope(
        ts,
        "response_item",
        {
            "type": "function_call",
            "name": name,
            "arguments": json.dumps(arguments),
        },
    )


def function_call_output(ts: str, output: str) -> Dict:
    return _envelope(
        ts,
        "response_item",
        {"type": "function_call_output", "output": output},
    )


def compacted_entry(ts: str, summary: str) -> Dict:
    return _envelope(ts, "compacted", {"message": summary})


def agent_message_event(ts: str, text: str) -> Dict:
    """event_msg.agent_message mirror — walker must silently skip this."""
    return _envelope(
        ts, "event_msg", {"type": "agent_message", "message": text}
    )


# ── Session compositions ──────────────────────────────────────────────

AGENTS_INJECTION = (
    "<permissions>read/write allowed</permissions>\n"
    "AGENTS.md contents follow:\nYou are a coding assistant."
)


def _write_rollout(path: Path, lines: List[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def build_normal_session() -> List[Dict]:
    """Plain user/assistant turns, one injected noise line to ensure it's skipped."""
    return [
        session_meta("019d0000-0000-7000-0000-000000000001", "2026-04-10T10:00:00Z"),
        turn_context("2026-04-10T10:00:01Z"),
        user_role_injection("2026-04-10T10:00:02Z", AGENTS_INJECTION),
        user_message("2026-04-10T10:00:03Z", "How do I handle Python errors?"),
        assistant_message(
            "2026-04-10T10:00:04Z",
            "Use try/except blocks for control flow around failures.",
        ),
        agent_message_event("2026-04-10T10:00:05Z", "(short commentary mirror)"),
        user_message("2026-04-10T10:00:06Z", "What about multiple exception types?"),
        assistant_message(
            "2026-04-10T10:00:07Z",
            "You can list them in a tuple: except (ValueError, KeyError):",
        ),
    ]


def build_detailed_session() -> List[Dict]:
    """Session that exercises tool_use/tool_result in detailed mode."""
    return [
        session_meta(
            "019d0000-0000-7000-0000-000000000002",
            "2026-04-10T11:00:00Z",
            cwd="/home/test/detailed",
        ),
        turn_context("2026-04-10T11:00:01Z"),
        user_message("2026-04-10T11:00:02Z", "Read the README.md file please."),
        assistant_message(
            "2026-04-10T11:00:03Z", "I'll read it with the Read tool."
        ),
        function_call(
            "2026-04-10T11:00:04Z",
            "Read",
            {"file_path": "/home/test/detailed/README.md"},
        ),
        function_call_output("2026-04-10T11:00:05Z", "# Project\nHello."),
        assistant_message(
            "2026-04-10T11:00:06Z", "The README says 'Hello'."
        ),
    ]


def build_parent_session(parent_id: str) -> List[Dict]:
    """Parent session that will spawn a subagent."""
    return [
        session_meta(parent_id, "2026-04-10T12:00:00Z", cwd="/home/test/parent"),
        turn_context("2026-04-10T12:00:01Z"),
        user_message("2026-04-10T12:00:02Z", "Run the reviewer subagent on this PR."),
        assistant_message(
            "2026-04-10T12:00:03Z", "Spawning the reviewer subagent now."
        ),
    ]


def build_subagent_session(parent_id: str, subagent_id: str) -> List[Dict]:
    """Subagent session linked via parent_thread_id in session_meta."""
    return [
        session_meta(
            subagent_id,
            "2026-04-10T12:00:10Z",
            cwd="/home/test/parent",
            subagent_parent_id=parent_id,
            agent_nickname="Carson",
            agent_role="code-reviewer",
        ),
        turn_context("2026-04-10T12:00:11Z"),
        user_message(
            "2026-04-10T12:00:12Z", "Review PR #42 for merge safety."
        ),
        assistant_message(
            "2026-04-10T12:00:13Z",
            "The PR looks safe. No destructive migrations.",
        ),
    ]


def build_compacted_session() -> List[Dict]:
    """Session with a compacted entry (detailed mode renders it)."""
    return [
        session_meta(
            "019d0000-0000-7000-0000-000000000005", "2026-04-10T13:00:00Z"
        ),
        turn_context("2026-04-10T13:00:01Z"),
        user_message("2026-04-10T13:00:02Z", "Continue from the previous session."),
        compacted_entry(
            "2026-04-10T13:00:03Z",
            "Previous session: user asked about CI config and got 3 fixes.",
        ),
        assistant_message(
            "2026-04-10T13:00:04Z", "Picking up where we left off."
        ),
    ]


def build_reasoning_only_session() -> List[Dict]:
    """Session with reasoning entries — must be skipped entirely."""
    return [
        session_meta(
            "019d0000-0000-7000-0000-000000000006", "2026-04-10T14:00:00Z"
        ),
        turn_context("2026-04-10T14:00:01Z"),
        user_message("2026-04-10T14:00:02Z", "Think about this problem."),
        reasoning_item("2026-04-10T14:00:03Z", "<<server-side-opaque>>"),
        reasoning_item("2026-04-10T14:00:04Z", "<<another-opaque-blob>>"),
        assistant_message("2026-04-10T14:00:05Z", "Here is my answer."),
    ]


def build_with_developer_session() -> List[Dict]:
    """Session with a developer-role message (skipped in normal, shown in detailed)."""
    return [
        session_meta(
            "019d0000-0000-7000-0000-000000000007", "2026-04-10T15:00:00Z"
        ),
        turn_context("2026-04-10T15:00:01Z"),
        developer_message(
            "2026-04-10T15:00:02Z",
            "Sandbox mode: read-only. Permissions: no writes to /etc.",
        ),
        user_message("2026-04-10T15:00:03Z", "Show me the permissions."),
        assistant_message(
            "2026-04-10T15:00:04Z",
            "Sandbox is read-only and /etc is blocked from writes.",
        ),
    ]


# ── Public fixture API ────────────────────────────────────────────────

# Pre-chosen UUIDs so the session_index file can reference the parent.
PARENT_SESSION_ID = "019d0000-0000-7000-0000-000000000003"
SUBAGENT_SESSION_ID = "019d0000-0000-7000-0000-000000000004"
PARENT_THREAD_NAME = "request-review run"


class CodexFixtures:
    """Create a temp ~/.codex/ layout with seven synthetic rollout files."""

    @staticmethod
    def create_test_environment() -> (
        "tuple[str, Dict[str, Path], Path]"
    ):
        """Build the fixture tree.

        Returns ``(temp_dir, files, session_index_path)`` where ``files``
        maps a category name to the rollout file Path. Tests that want to
        exercise ``_read_session_index`` should patch
        ``codex_metadata.SESSION_INDEX_PATH`` to ``session_index_path``.
        """
        temp_dir = tempfile.mkdtemp()
        base = Path(temp_dir) / ".codex"
        date_dir = base / "sessions" / "2026" / "04" / "10"
        date_dir.mkdir(parents=True)

        files: Dict[str, Path] = {}

        normal = build_normal_session()
        files["normal"] = (
            date_dir / "rollout-2026-04-10T10-00-00-019d0000-0000-7000-0000-000000000001.jsonl"
        )
        _write_rollout(files["normal"], normal)

        detailed = build_detailed_session()
        files["detailed"] = (
            date_dir / "rollout-2026-04-10T11-00-00-019d0000-0000-7000-0000-000000000002.jsonl"
        )
        _write_rollout(files["detailed"], detailed)

        parent = build_parent_session(PARENT_SESSION_ID)
        files["parent"] = (
            date_dir / f"rollout-2026-04-10T12-00-00-{PARENT_SESSION_ID}.jsonl"
        )
        _write_rollout(files["parent"], parent)

        subagent = build_subagent_session(PARENT_SESSION_ID, SUBAGENT_SESSION_ID)
        files["subagent"] = (
            date_dir / f"rollout-2026-04-10T12-00-10-{SUBAGENT_SESSION_ID}.jsonl"
        )
        _write_rollout(files["subagent"], subagent)

        compacted = build_compacted_session()
        files["compacted"] = (
            date_dir / "rollout-2026-04-10T13-00-00-019d0000-0000-7000-0000-000000000005.jsonl"
        )
        _write_rollout(files["compacted"], compacted)

        reasoning_only = build_reasoning_only_session()
        files["reasoning_only"] = (
            date_dir / "rollout-2026-04-10T14-00-00-019d0000-0000-7000-0000-000000000006.jsonl"
        )
        _write_rollout(files["reasoning_only"], reasoning_only)

        with_dev = build_with_developer_session()
        files["with_developer"] = (
            date_dir / "rollout-2026-04-10T15-00-00-019d0000-0000-7000-0000-000000000007.jsonl"
        )
        _write_rollout(files["with_developer"], with_dev)

        session_index_path = base / "session_index.jsonl"
        with open(session_index_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": PARENT_SESSION_ID,
                "thread_name": PARENT_THREAD_NAME,
            }) + "\n")

        return temp_dir, files, session_index_path

    @staticmethod
    def codex_sessions_root(temp_dir: str) -> Path:
        """Return the ``~/.codex/sessions`` root for a fixture temp dir."""
        return Path(temp_dir) / ".codex" / "sessions"


def cleanup_test_environment(temp_dir: str) -> None:
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
