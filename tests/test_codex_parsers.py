#!/usr/bin/env python3
"""Unit tests for src/codex_parsers.py."""

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))
sys.path.append(str(Path(__file__).parent))

from fixtures.sample_codex_conversations import (  # noqa: E402
    CodexFixtures,
    cleanup_test_environment,
)
import codex_parsers  # noqa: E402


class TestCodexPassthroughHelpers(unittest.TestCase):
    """Trivial helpers — ``is_ide_preamble`` and ``clean_slash_command``."""

    def test_is_ide_preamble_always_false(self):
        self.assertFalse(codex_parsers.is_ide_preamble(""))
        self.assertFalse(codex_parsers.is_ide_preamble("any string"))
        self.assertFalse(codex_parsers.is_ide_preamble("<command-name>/foo"))

    def test_clean_slash_command_is_identity(self):
        self.assertEqual(codex_parsers.clean_slash_command("/foo bar"), "/foo bar")
        self.assertEqual(codex_parsers.clean_slash_command(""), "")


class TestExtractTextContent(unittest.TestCase):
    """``extract_text_content`` handles the three content shapes Codex uses."""

    def test_string_passthrough(self):
        self.assertEqual(codex_parsers.extract_text_content("hello"), "hello")

    def test_list_of_typed_items(self):
        content = [
            {"type": "input_text", "text": "part 1"},
            {"type": "output_text", "text": "part 2"},
            {"type": "summary_text", "text": "part 3"},
        ]
        self.assertEqual(
            codex_parsers.extract_text_content(content), "part 1\npart 2\npart 3"
        )

    def test_list_unknown_item_types_are_skipped(self):
        content = [
            {"type": "input_text", "text": "keep"},
            {"type": "image", "url": "ignored"},
        ]
        self.assertEqual(codex_parsers.extract_text_content(content), "keep")

    def test_none_returns_empty(self):
        self.assertEqual(codex_parsers.extract_text_content(None), "")


class TestExtractConversation(unittest.TestCase):
    """``extract_conversation`` walker rules against fixture rollouts."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, _ = CodexFixtures.create_test_environment()

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def test_normal_session_yields_alternating_user_assistant(self):
        conv = codex_parsers.extract_conversation(self.files["normal"])
        self.assertEqual([m["role"] for m in conv], ["user", "assistant"] * 2)
        self.assertIn("Python errors", conv[0]["content"])
        self.assertIn("try/except", conv[1]["content"])

    def test_agents_md_injection_is_skipped(self):
        """response_item role=user with AGENTS.md markers must not appear."""
        conv = codex_parsers.extract_conversation(self.files["normal"])
        joined = "\n".join(m["content"] for m in conv)
        self.assertNotIn("AGENTS.md", joined)
        self.assertNotIn("<permissions>", joined)

    def test_agent_message_mirror_is_skipped(self):
        conv = codex_parsers.extract_conversation(self.files["normal"])
        joined = "\n".join(m["content"] for m in conv)
        self.assertNotIn("(short commentary mirror)", joined)

    def test_reasoning_entries_always_skipped(self):
        conv = codex_parsers.extract_conversation(
            self.files["reasoning_only"], detailed=True
        )
        self.assertEqual([m["role"] for m in conv], ["user", "assistant"])

    def test_developer_skipped_in_normal_mode(self):
        conv = codex_parsers.extract_conversation(
            self.files["with_developer"], detailed=False
        )
        self.assertNotIn("system", [m["role"] for m in conv])

    def test_developer_included_in_detailed_mode(self):
        conv = codex_parsers.extract_conversation(
            self.files["with_developer"], detailed=True
        )
        roles = [m["role"] for m in conv]
        self.assertIn("system", roles)
        system_msg = next(m for m in conv if m["role"] == "system")
        self.assertTrue(system_msg["content"].startswith("[developer] "))

    def test_developer_truncated_above_2000_chars(self):
        """Developer messages longer than 2000 chars should be truncated."""
        import json
        import tempfile

        long_text = "x" * 3000
        entries = [
            {
                "timestamp": "2026-04-10T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "dev-long",
                    "cwd": "/tmp",
                    "cli_version": "0.1",
                    "timestamp": "2026-04-10T00:00:00Z",
                    "model": "gpt-5-codex",
                    "model_provider": "openai",
                },
            },
            {
                "timestamp": "2026-04-10T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": long_text}],
                },
            },
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            tmp = f.name
        try:
            conv = codex_parsers.extract_conversation(Path(tmp), detailed=True)
            system_msg = next(m for m in conv if m["role"] == "system")
            self.assertIn("[truncated]", system_msg["content"])
            self.assertLess(len(system_msg["content"]), 2100)
        finally:
            Path(tmp).unlink()

    def test_tool_calls_in_detailed_mode(self):
        conv = codex_parsers.extract_conversation(
            self.files["detailed"], detailed=True
        )
        roles = [m["role"] for m in conv]
        self.assertIn("tool_use", roles)
        self.assertIn("tool_result", roles)
        tool_use = next(m for m in conv if m["role"] == "tool_use")
        self.assertIn("🔧 Tool: Read", tool_use["content"])
        self.assertIn("/home/test/detailed/README.md", tool_use["content"])
        tool_result = next(m for m in conv if m["role"] == "tool_result")
        self.assertIn("📤 Result:", tool_result["content"])
        self.assertIn("# Project", tool_result["content"])

    def test_tool_calls_skipped_in_normal_mode(self):
        conv = codex_parsers.extract_conversation(
            self.files["detailed"], detailed=False
        )
        roles = [m["role"] for m in conv]
        self.assertNotIn("tool_use", roles)
        self.assertNotIn("tool_result", roles)

    def test_compacted_rendered_only_in_detailed_mode(self):
        normal = codex_parsers.extract_conversation(self.files["compacted"])
        self.assertNotIn(
            "compaction", "\n".join(m["content"] for m in normal)
        )

        detailed = codex_parsers.extract_conversation(
            self.files["compacted"], detailed=True
        )
        sys_msgs = [m for m in detailed if m["role"] == "system"]
        self.assertEqual(len(sys_msgs), 1)
        self.assertTrue(sys_msgs[0]["content"].startswith("[compaction]"))

    def test_malformed_lines_are_skipped(self):
        import tempfile
        content = "not valid json\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write(content)
            tmp = f.name
        try:
            conv = codex_parsers.extract_conversation(Path(tmp))
            self.assertEqual(conv, [])
        finally:
            Path(tmp).unlink()


class TestExtractFirstUserText(unittest.TestCase):
    """``extract_first_user_text`` must skip injection and return the first real turn."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, _ = CodexFixtures.create_test_environment()

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def test_returns_first_event_msg_user_message(self):
        text = codex_parsers.extract_first_user_text(self.files["normal"])
        self.assertIn("Python errors", text)

    def test_skips_agents_injection(self):
        """The walker must not return the response_item role=user injection."""
        text = codex_parsers.extract_first_user_text(self.files["normal"])
        self.assertNotIn("AGENTS.md", text)
        self.assertNotIn("<permissions>", text)

    def test_truncates_to_100_chars(self):
        self.assertLessEqual(
            len(codex_parsers.extract_first_user_text(self.files["normal"])), 100
        )


class TestConversationPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir, cls.files, _ = CodexFixtures.create_test_environment()

    @classmethod
    def tearDownClass(cls):
        cleanup_test_environment(cls.temp_dir)

    def test_preview_counts_user_and_assistant_only(self):
        preview, count = codex_parsers.get_conversation_preview(self.files["normal"])
        # Normal session has 2 user + 2 assistant real turns.
        self.assertEqual(count, 4)
        self.assertIn("Python errors", preview)

    def test_preview_skips_injection_for_preview_text(self):
        preview, _ = codex_parsers.get_conversation_preview(self.files["normal"])
        self.assertNotIn("AGENTS.md", preview)


class TestExtractSearchContent(unittest.TestCase):
    """``extract_search_content`` return shapes for each envelope type."""

    def test_user_message_returns_human_speaker(self):
        entry = {
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "hello world"},
        }
        result = codex_parsers.extract_search_content(entry)
        self.assertEqual(result, ("hello world", "human"))

    def test_assistant_message_returns_assistant_speaker(self):
        entry = {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "hi there"}],
            },
        }
        result = codex_parsers.extract_search_content(entry)
        self.assertEqual(result, ("hi there", "assistant"))

    def test_injection_user_returns_none(self):
        entry = {
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "<permissions>read/write</permissions>",
            },
        }
        self.assertIsNone(codex_parsers.extract_search_content(entry))

    def test_reasoning_returns_none(self):
        entry = {
            "type": "response_item",
            "payload": {"type": "reasoning", "encrypted_content": "..."},
        }
        self.assertIsNone(codex_parsers.extract_search_content(entry))

    def test_response_item_role_user_returns_none(self):
        """Avoid double-indexing user content via the AGENTS.md mirror."""
        entry = {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            },
        }
        self.assertIsNone(codex_parsers.extract_search_content(entry))

    def test_non_dict_entry_returns_none(self):
        self.assertIsNone(codex_parsers.extract_search_content("not a dict"))
        self.assertIsNone(codex_parsers.extract_search_content(None))


class TestDetailedCatchAllAndWebSearch(unittest.TestCase):
    """Detailed mode surfaces novel response_item types and web_search calls."""

    def _write(self, entries) -> Path:
        import json
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            return Path(f.name)

    def test_unknown_response_item_type_surfaces_in_detailed_mode(self):
        tmp = self._write([
            {
                "timestamp": "2026-04-10T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "x", "cwd": "/", "cli_version": "0.1"},
            },
            {
                "timestamp": "2026-04-10T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "totally_new_envelope"},
            },
        ])
        try:
            conv = codex_parsers.extract_conversation(tmp, detailed=True)
            skipped = [m for m in conv if m["role"] == "system"
                       and "skipped" in m["content"]]
            self.assertEqual(len(skipped), 1)
            self.assertIn("totally_new_envelope", skipped[0]["content"])
        finally:
            tmp.unlink()

    def test_unknown_response_item_type_silent_in_normal_mode(self):
        tmp = self._write([
            {
                "timestamp": "2026-04-10T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "x", "cwd": "/", "cli_version": "0.1"},
            },
            {
                "timestamp": "2026-04-10T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "totally_new_envelope"},
            },
        ])
        try:
            conv = codex_parsers.extract_conversation(tmp, detailed=False)
            self.assertEqual(conv, [])
        finally:
            tmp.unlink()

    def test_web_search_call_rendered_as_tool_use(self):
        tmp = self._write([
            {
                "timestamp": "2026-04-10T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "x", "cwd": "/", "cli_version": "0.1"},
            },
            {
                "timestamp": "2026-04-10T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "web_search_call",
                    "action": {"query": "python decorators"},
                },
            },
        ])
        try:
            conv = codex_parsers.extract_conversation(tmp, detailed=True)
            tool_uses = [m for m in conv if m["role"] == "tool_use"]
            self.assertEqual(len(tool_uses), 1)
            self.assertIn("web_search", tool_uses[0]["content"])
            self.assertIn("python decorators", tool_uses[0]["content"])
        finally:
            tmp.unlink()


class TestFormatToolInput(unittest.TestCase):
    """``_format_tool_input`` passes through multi-line strings unchanged."""

    def test_multiline_string_passthrough(self):
        raw = '{\n  "file_path": "/a/b"\n}'
        result = codex_parsers._format_tool_input(raw)
        self.assertEqual(result, raw)

    def test_empty_string_returns_empty(self):
        self.assertEqual(codex_parsers._format_tool_input(""), "")

    def test_compact_json_string_is_pretty_printed(self):
        raw = '{"file_path":"/a/b"}'
        result = codex_parsers._format_tool_input(raw)
        self.assertIn("\n", result)
        self.assertIn("file_path", result)

    def test_plain_string_falls_through(self):
        self.assertEqual(codex_parsers._format_tool_input("hello"), "hello")

    def test_dict_is_pretty_printed(self):
        result = codex_parsers._format_tool_input({"k": "v"})
        self.assertIn("\n", result)
        self.assertIn('"k"', result)


if __name__ == "__main__":
    unittest.main()
