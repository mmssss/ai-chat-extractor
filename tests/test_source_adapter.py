#!/usr/bin/env python3
"""Unit tests for src/source_adapter.py."""

import unittest

from ai_chat_extractor import codex_metadata, codex_parsers, metadata, parsers
from ai_chat_extractor.source_adapter import (
    SOURCES,
    SourceAdapter,
    get_source,
)


class TestGetSource(unittest.TestCase):
    """``get_source`` returns the right adapter for known names, raises otherwise."""

    def test_claude_adapter_fields(self):
        adapter = get_source("claude")
        self.assertIsInstance(adapter, SourceAdapter)
        self.assertEqual(adapter.name, "claude")
        self.assertEqual(adapter.display_name, "Claude")
        self.assertEqual(adapter.filename_prefix, "claude")
        self.assertIs(adapter.parsers, parsers)
        self.assertIs(adapter.metadata, metadata)
        self.assertEqual(adapter.default_source_dir.name, "projects")

    def test_codex_adapter_fields(self):
        adapter = get_source("codex")
        self.assertEqual(adapter.name, "codex")
        self.assertEqual(adapter.display_name, "Codex")
        self.assertEqual(adapter.filename_prefix, "codex")
        self.assertIs(adapter.parsers, codex_parsers)
        self.assertIs(adapter.metadata, codex_metadata)
        self.assertEqual(adapter.default_source_dir.name, "sessions")

    def test_claude_and_codex_have_disjoint_cache_dirs(self):
        """Per-source search cache must not collide."""
        claude = get_source("claude")
        codex = get_source("codex")
        self.assertNotEqual(claude.cache_subdir, codex.cache_subdir)

    def test_output_dir_suggestions_are_source_flavored(self):
        """Suggestions should mention the assistant in folder names."""
        claude_names = {p.name for p in get_source("claude").output_dir_suggestions}
        codex_names = {p.name for p in get_source("codex").output_dir_suggestions}
        self.assertTrue(all("Claude" in n for n in claude_names))
        self.assertTrue(all("Codex" in n for n in codex_names))

    def test_unknown_source_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_source("gemini")
        # Error message should mention the bad name and the known set
        self.assertIn("gemini", str(ctx.exception))
        self.assertIn("claude", str(ctx.exception))
        self.assertIn("codex", str(ctx.exception))

    def test_registry_keys_are_exactly_claude_and_codex(self):
        self.assertEqual(set(SOURCES.keys()), {"claude", "codex"})

    def test_adapter_is_frozen(self):
        adapter = get_source("claude")
        with self.assertRaises(Exception):
            adapter.display_name = "Different"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
