#!/usr/bin/env python3
"""Integration tests for ConversationExtractor with source="codex"."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).parent.parent / "src"))
sys.path.append(str(Path(__file__).parent))

from fixtures.sample_codex_conversations import (  # noqa: E402
    CodexFixtures,
    PARENT_SESSION_ID,
    PARENT_THREAD_NAME,
    cleanup_test_environment,
)
import codex_metadata  # noqa: E402
from conversation_extractor import ConversationExtractor  # noqa: E402


class CodexExtractorBase(unittest.TestCase):
    """Shared setup — build fixture tree once, fresh output dir per test."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, cls.index_path = (
            CodexFixtures.create_test_environment()
        )
        cls.sessions_root = CodexFixtures.codex_sessions_root(cls.temp_dir)

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def setUp(self):
        self.output_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def _make_extractor(self) -> ConversationExtractor:
        return ConversationExtractor(
            output_dir=self.output_dir,
            source_dir=self.sessions_root,
            source="codex",
        )


class TestCodexExtractorInit(CodexExtractorBase):
    def test_adapter_is_codex(self):
        ex = self._make_extractor()
        self.assertEqual(ex.source, "codex")
        self.assertEqual(ex.adapter.name, "codex")
        self.assertEqual(ex.adapter.display_name, "Codex")

    def test_session_dir_routes_to_fixture_tree(self):
        ex = self._make_extractor()
        self.assertEqual(ex.session_dir, self.sessions_root)

    def test_default_source_claude_unaffected(self):
        """Instantiating without source must still default to Claude."""
        ex = ConversationExtractor(
            output_dir=self.output_dir, source_dir=self.sessions_root
        )
        self.assertEqual(ex.source, "claude")


class TestCodexFindSessions(CodexExtractorBase):
    def test_find_sessions_excludes_subagents_by_default(self):
        ex = self._make_extractor()
        sessions = ex.find_sessions()
        self.assertEqual(len(sessions), 6)

    def test_find_sessions_include_subagents(self):
        ex = self._make_extractor()
        sessions = ex.find_sessions(include_subagents=True)
        self.assertEqual(len(sessions), 7)

    def test_find_subagents_returns_codex_subagent(self):
        ex = self._make_extractor()
        subs = ex.find_subagents(self.files["parent"])
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0], self.files["subagent"])


class TestCodexExtractConversation(CodexExtractorBase):
    def test_extract_normal_session(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["normal"])
        self.assertEqual([m["role"] for m in conv], ["user", "assistant"] * 2)

    def test_extract_detailed_session(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["detailed"], detailed=True)
        roles = [m["role"] for m in conv]
        self.assertIn("tool_use", roles)
        self.assertIn("tool_result", roles)


class TestCodexSaveAsMarkdown(CodexExtractorBase):
    def test_markdown_filename_has_codex_prefix(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["normal"])
        path = ex.save_as_markdown(
            conv, self.files["normal"].stem, session_path=self.files["normal"]
        )
        self.assertIsNotNone(path)
        assert path is not None  # for type checker
        self.assertIn("_codex_", path.name)
        self.assertTrue(path.name.endswith(".md"))

    def test_markdown_h1_says_codex(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["normal"])
        path = ex.save_as_markdown(
            conv, self.files["normal"].stem, session_path=self.files["normal"]
        )
        assert path is not None
        content = path.read_text()
        self.assertIn("# Codex Conversation Log", content)
        self.assertNotIn("# Claude Conversation Log", content)

    def test_markdown_assistant_header_uses_codex_label(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["normal"])
        path = ex.save_as_markdown(
            conv, self.files["normal"].stem, session_path=self.files["normal"]
        )
        assert path is not None
        content = path.read_text()
        self.assertIn("🤖 Codex", content)
        self.assertNotIn("🤖 Claude", content)


class TestCodexSaveAsJson(CodexExtractorBase):
    def test_json_filename_has_codex_prefix(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["detailed"])
        path = ex.save_as_json(
            conv, self.files["detailed"].stem, session_path=self.files["detailed"]
        )
        assert path is not None
        self.assertIn("_codex_", path.name)
        self.assertTrue(path.name.endswith(".json"))


class TestCodexSaveAsHtml(CodexExtractorBase):
    def test_html_title_and_h1_use_codex(self):
        ex = self._make_extractor()
        conv = ex.extract_conversation(self.files["normal"])
        path = ex.save_as_html(
            conv, self.files["normal"].stem, session_path=self.files["normal"]
        )
        assert path is not None
        self.assertIn("_codex_", path.name)
        content = path.read_text()
        self.assertIn("Codex Conversation", content)
        self.assertIn("🤖 Codex", content)


class TestCodexSubagentFilename(CodexExtractorBase):
    def test_subagent_filename_embeds_parent_slug_and_nickname(self):
        """Verify generate_subagent_filename routes through the Codex adapter."""
        ex = self._make_extractor()
        parent_meta = ex.extract_session_metadata(self.files["parent"])
        sa_filename = ex.generate_subagent_filename(
            self.files["subagent"], parent_meta, agent_index=1, format="markdown"
        )
        # Prefix should be codex, not claude
        self.assertIn("_codex_", sa_filename)
        self.assertNotIn("_claude_", sa_filename)
        # Nickname + short UUID from session_meta must be present
        self.assertIn("Carson", sa_filename)
        # Agent index marker
        self.assertIn("agent1", sa_filename)
        self.assertTrue(sa_filename.endswith(".md"))


class TestCodexMetadataIntegration(CodexExtractorBase):
    """Smoke test that the extractor routes metadata calls through the Codex module."""

    def test_extract_session_metadata_returns_codex_schema(self):
        ex = self._make_extractor()
        meta = ex.extract_session_metadata(self.files["parent"])
        self.assertEqual(meta["sessionId"], PARENT_SESSION_ID)
        self.assertEqual(meta["models"], ["gpt-5-codex"])
        self.assertTrue(meta["has_subagents"])

    def test_custom_title_resolves_via_session_index(self):
        """End-to-end: the extractor must pick up the thread name mapping."""
        ex = self._make_extractor()
        codex_metadata._read_session_index.cache_clear()
        with patch.object(
            codex_metadata, "SESSION_INDEX_PATH", new=self.index_path
        ):
            meta = ex.extract_session_metadata(self.files["parent"])
        self.assertEqual(meta["custom_title"], PARENT_THREAD_NAME)
        codex_metadata._read_session_index.cache_clear()


class TestClaudeRegressionUnaffected(unittest.TestCase):
    """A Claude extractor must still produce Claude-labeled output after the refactor."""

    def setUp(self):
        self.output_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_claude_extractor_uses_claude_labels(self):
        """Build a minimal Claude session and verify it still saves with claude_ prefix."""
        import json

        claude_session_dir = self.output_dir / ".claude" / "projects" / "p1"
        claude_session_dir.mkdir(parents=True)
        session_file = claude_session_dir / "test_claude_session.jsonl"
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2024-01-01T10:00:00Z",
            }) + "\n")
            f.write(json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hi there"}],
                },
                "timestamp": "2024-01-01T10:01:00Z",
            }) + "\n")

        ex = ConversationExtractor(
            output_dir=self.output_dir / "out",
            source_dir=self.output_dir / ".claude" / "projects",
            source="claude",
        )
        conv = ex.extract_conversation(session_file)
        self.assertGreater(len(conv), 0)
        path = ex.save_as_markdown(
            conv, session_file.stem, session_path=session_file
        )
        assert path is not None
        self.assertIn("_claude_", path.name)
        content = path.read_text()
        self.assertIn("# Claude Conversation Log", content)
        self.assertIn("🤖 Claude", content)


if __name__ == "__main__":
    unittest.main()
