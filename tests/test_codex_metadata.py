#!/usr/bin/env python3
"""Unit tests for src/codex_metadata.py."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).parent.parent / "src"))
sys.path.append(str(Path(__file__).parent))

from fixtures.sample_codex_conversations import (  # noqa: E402
    CodexFixtures,
    PARENT_SESSION_ID,
    PARENT_THREAD_NAME,
    SUBAGENT_SESSION_ID,
    cleanup_test_environment,
)
import codex_metadata  # noqa: E402


class TestFindSessions(unittest.TestCase):
    """``find_sessions`` discovers rollouts and filters subagents by default."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, _ = CodexFixtures.create_test_environment()
        cls.sessions_root = CodexFixtures.codex_sessions_root(cls.temp_dir)

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def test_find_top_level_sessions_excludes_subagents(self):
        sessions = codex_metadata.find_sessions(self.sessions_root)
        names = {p.name for p in sessions}
        self.assertNotIn(self.files["subagent"].name, names)
        # 7 total files minus 1 subagent = 6
        self.assertEqual(len(sessions), 6)

    def test_find_sessions_with_include_subagents(self):
        sessions = codex_metadata.find_sessions(
            self.sessions_root, include_subagents=True
        )
        self.assertEqual(len(sessions), 7)
        names = {p.name for p in sessions}
        self.assertIn(self.files["subagent"].name, names)

    def test_find_sessions_sorted_by_mtime_desc(self):
        sessions = codex_metadata.find_sessions(self.sessions_root)
        mtimes = [p.stat().st_mtime for p in sessions]
        self.assertEqual(mtimes, sorted(mtimes, reverse=True))

    def test_find_sessions_nonexistent_dir_returns_empty(self):
        sessions = codex_metadata.find_sessions(Path("/nonexistent/path/xyz"))
        self.assertEqual(sessions, [])


class TestFindSubagents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, _ = CodexFixtures.create_test_environment()

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def test_parent_session_finds_one_subagent(self):
        subs = codex_metadata.find_subagents(self.files["parent"])
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0], self.files["subagent"])

    def test_non_parent_session_finds_no_subagents(self):
        subs = codex_metadata.find_subagents(self.files["normal"])
        self.assertEqual(subs, [])


class TestGetSubagentMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, _ = CodexFixtures.create_test_environment()

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def test_subagent_metadata_populates_expected_keys(self):
        meta = codex_metadata.get_subagent_metadata(self.files["subagent"])
        self.assertEqual(meta["agentId"], SUBAGENT_SESSION_ID)
        self.assertEqual(meta["agentType"], "code-reviewer")
        self.assertEqual(meta["agent_nickname"], "Carson")
        # Display format: <nickname>_<8-char-short-uuid>
        self.assertEqual(meta["agent_id_display"], "Carson_019d0000")
        self.assertGreater(meta["entry_count"], 0)
        self.assertEqual(meta["first_message"], "Review PR #42 for merge safety.")

    def test_subagent_metadata_on_missing_file(self):
        meta = codex_metadata.get_subagent_metadata(Path("/nonexistent.jsonl"))
        self.assertEqual(meta["agentId"], "")
        self.assertEqual(meta["agent_id_display"], "unknown")


class TestExtractSessionMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, cls.index_path = (
            CodexFixtures.create_test_environment()
        )

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def _clear_index_cache(self):
        codex_metadata._read_session_index.cache_clear()

    def test_parent_metadata_has_expected_keys(self):
        meta = codex_metadata.extract_session_metadata(self.files["parent"])
        self.assertEqual(meta["sessionId"], PARENT_SESSION_ID)
        self.assertEqual(meta["cwd"], "/home/test/parent")
        self.assertEqual(meta["version"], "0.20.0")
        self.assertEqual(meta["models"], ["gpt-5-codex"])
        self.assertTrue(meta["has_subagents"])
        self.assertEqual(meta["subagent_count"], 1)
        self.assertGreater(meta["entry_count"], 0)

    def test_normal_session_has_no_subagents(self):
        meta = codex_metadata.extract_session_metadata(self.files["normal"])
        self.assertFalse(meta["has_subagents"])
        self.assertEqual(meta["subagent_count"], 0)

    def test_first_user_message_extracted(self):
        meta = codex_metadata.extract_session_metadata(self.files["normal"])
        self.assertIn("Python errors", meta["first_user_message"])
        self.assertNotIn("AGENTS.md", meta["first_user_message"])

    def test_custom_title_from_session_index(self):
        """``custom_title`` should be populated by patching SESSION_INDEX_PATH."""
        self._clear_index_cache()
        with patch.object(
            codex_metadata, "SESSION_INDEX_PATH", new=self.index_path
        ):
            meta = codex_metadata.extract_session_metadata(self.files["parent"])
        self.assertEqual(meta["custom_title"], PARENT_THREAD_NAME)
        self._clear_index_cache()

    def test_custom_title_absent_without_session_index(self):
        self._clear_index_cache()
        with patch.object(
            codex_metadata,
            "SESSION_INDEX_PATH",
            new=Path("/nonexistent/session_index.jsonl"),
        ):
            meta = codex_metadata.extract_session_metadata(self.files["parent"])
        self.assertEqual(meta["custom_title"], "")
        self._clear_index_cache()


class TestReadSessionIndex(unittest.TestCase):
    """Last-write-wins behavior of the session_index reader."""

    def test_reads_uuid_to_thread_name_mapping(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write(json.dumps({"id": "abc", "thread_name": "first"}) + "\n")
            f.write(json.dumps({"id": "xyz", "thread_name": "other"}) + "\n")
            # last-write-wins for the same id
            f.write(json.dumps({"id": "abc", "thread_name": "final"}) + "\n")
            tmp = Path(f.name)
        try:
            codex_metadata._read_session_index.cache_clear()
            with patch.object(codex_metadata, "SESSION_INDEX_PATH", new=tmp):
                mapping = codex_metadata._read_session_index()
            self.assertEqual(mapping["abc"], "final")
            self.assertEqual(mapping["xyz"], "other")
        finally:
            codex_metadata._read_session_index.cache_clear()
            tmp.unlink()

    def test_missing_index_returns_empty_dict(self):
        codex_metadata._read_session_index.cache_clear()
        with patch.object(
            codex_metadata,
            "SESSION_INDEX_PATH",
            new=Path("/definitely/not/here.jsonl"),
        ):
            mapping = codex_metadata._read_session_index()
        self.assertEqual(mapping, {})
        codex_metadata._read_session_index.cache_clear()


class TestReadSessionMetaHardening(unittest.TestCase):
    """``_read_session_meta`` must not crash on non-object JSON roots."""

    def _write(self, first_line: str) -> Path:
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write(first_line + "\n")
            return Path(f.name)

    def test_json_array_root_returns_none(self):
        tmp = self._write("[1, 2, 3]")
        try:
            self.assertIsNone(codex_metadata._read_session_meta(tmp))
        finally:
            tmp.unlink()

    def test_json_string_root_returns_none(self):
        tmp = self._write('"just a string"')
        try:
            self.assertIsNone(codex_metadata._read_session_meta(tmp))
        finally:
            tmp.unlink()

    def test_json_number_root_returns_none(self):
        tmp = self._write("42")
        try:
            self.assertIsNone(codex_metadata._read_session_meta(tmp))
        finally:
            tmp.unlink()

    def test_is_subagent_file_on_non_dict_root_returns_false(self):
        """``find_sessions`` must not crash when a rollout has a non-dict first line."""
        tmp = self._write("[]")
        try:
            self.assertFalse(codex_metadata._is_subagent_file(tmp))
        finally:
            tmp.unlink()


class TestMessageCountAndNoProviderFallback(unittest.TestCase):
    """``extract_session_metadata`` surfaces message_count and avoids the
    old ``model_provider`` fallback that used to poison ``models``.
    """

    def test_message_count_separate_from_entry_count(self):
        meta = codex_metadata.extract_session_metadata(
            _build_tmp_normal_session()
        )
        # 2 user + 2 assistant turns in the normal fixture, plus envelope noise.
        self.assertEqual(meta["message_count"], 4)
        self.assertGreater(meta["entry_count"], meta["message_count"])

    def test_models_empty_when_no_real_model_seen(self):
        """When neither session_meta.model nor turn_context.model is present,
        ``models`` should be empty — not filled with the provider name."""
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write(json.dumps({
                "timestamp": "2026-04-10T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "no-model",
                    "cwd": "/tmp",
                    "cli_version": "0.1",
                    "timestamp": "2026-04-10T00:00:00Z",
                    "model_provider": "openai",
                },
            }) + "\n")
            tmp = Path(f.name)
        try:
            meta = codex_metadata.extract_session_metadata(tmp)
            self.assertEqual(meta["models"], [])
            self.assertNotIn("openai", meta["models"])
        finally:
            tmp.unlink()


def _build_tmp_normal_session() -> Path:
    """Helper: write a throwaway normal fixture rollout and return its path."""
    from fixtures.sample_codex_conversations import build_normal_session
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False
    ) as f:
        for entry in build_normal_session():
            f.write(json.dumps(entry) + "\n")
        return Path(f.name)


class TestFindSubagentsAcrossUtcBoundary(unittest.TestCase):
    """A subagent whose rollout landed in tomorrow's directory must still be found."""

    def setUp(self):
        import json
        import shutil
        import tempfile
        self._tempdir = tempfile.mkdtemp()
        self._shutil = shutil
        base = Path(self._tempdir) / ".codex" / "sessions" / "2026" / "04" / "10"
        base.mkdir(parents=True)
        next_day = Path(self._tempdir) / ".codex" / "sessions" / "2026" / "04" / "11"
        next_day.mkdir(parents=True)

        parent_id = "019d0000-0000-7000-0000-0000000000aa"
        subagent_id = "019d0000-0000-7000-0000-0000000000bb"

        parent_entries = [
            {
                "timestamp": "2026-04-10T23:59:30Z",
                "type": "session_meta",
                "payload": {
                    "id": parent_id,
                    "cwd": "/tmp",
                    "cli_version": "0.20.0",
                    "timestamp": "2026-04-10T23:59:30Z",
                    "model": "gpt-5-codex",
                    "model_provider": "openai",
                },
            },
        ]
        self.parent_path = (
            base / f"rollout-2026-04-10T23-59-30-{parent_id}.jsonl"
        )
        with open(self.parent_path, "w") as f:
            for e in parent_entries:
                f.write(json.dumps(e) + "\n")

        # Subagent spawned at 23:59:58 but rollout landed in the next day's dir.
        subagent_entries = [
            {
                "timestamp": "2026-04-11T00:00:01Z",
                "type": "session_meta",
                "payload": {
                    "id": subagent_id,
                    "cwd": "/tmp",
                    "cli_version": "0.20.0",
                    "timestamp": "2026-04-11T00:00:01Z",
                    "model": "gpt-5-codex",
                    "model_provider": "openai",
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": parent_id,
                                "agent_nickname": "Nyx",
                                "agent_role": "code-reviewer",
                            }
                        }
                    },
                },
            },
        ]
        self.subagent_path = (
            next_day / f"rollout-2026-04-11T00-00-01-{subagent_id}.jsonl"
        )
        with open(self.subagent_path, "w") as f:
            for e in subagent_entries:
                f.write(json.dumps(e) + "\n")

    def tearDown(self):
        self._shutil.rmtree(self._tempdir, ignore_errors=True)

    def test_next_day_subagent_is_discovered(self):
        subs = codex_metadata.find_subagents(self.parent_path)
        self.assertEqual(subs, [self.subagent_path])

    def test_non_date_parent_directory_does_not_crash(self):
        """Calling find_subagents on a file whose parent isn't YYYY/MM/DD
        must still work (falls back to just the parent dir)."""
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write("{}\n")
            tmp = Path(f.name)
        try:
            # No session_meta shape, so it returns [] — but must not raise.
            self.assertEqual(codex_metadata.find_subagents(tmp), [])
        finally:
            tmp.unlink()


if __name__ == "__main__":
    unittest.main()
