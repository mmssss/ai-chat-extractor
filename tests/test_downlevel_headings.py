"""Tests for heading handling in markdown export."""

import tempfile
import unittest
from pathlib import Path

from ai_chat_extractor.formatters import downlevel_headings, escape_headings, save_as_markdown


class TestDownlevelHeadings(unittest.TestCase):
    """Test the downlevel_headings function (used for assistant messages)."""

    def test_basic_downlevel(self):
        """# becomes ###, ## becomes ####."""
        text = "# Title\n## Subtitle\n### Section"
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, "### Title\n#### Subtitle\n##### Section")

    def test_caps_at_h6(self):
        """Headings can't go deeper than h6."""
        text = "##### H5\n###### H6"
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, "###### H5\n###### H6")

    def test_preserves_code_blocks(self):
        """Headings inside fenced code blocks are untouched."""
        text = "# Real heading\n```\n# comment in code\n```\n# Another heading"
        result = downlevel_headings(text, levels=2)
        self.assertEqual(
            result,
            "### Real heading\n```\n# comment in code\n```\n### Another heading"
        )

    def test_preserves_code_blocks_with_language(self):
        """Code fences with language tags are handled."""
        text = "```bash\n# shell comment\necho hello\n```"
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, "```bash\n# shell comment\necho hello\n```")

    def test_preserves_tilde_code_blocks(self):
        """~~~ fenced code blocks are also recognized."""
        text = "~~~\n# inside tilde block\n~~~\n# outside"
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, "~~~\n# inside tilde block\n~~~\n### outside")

    def test_no_headings(self):
        """Plain text passes through unchanged."""
        text = "Just some text\nwith multiple lines\nand no headings."
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, text)

    def test_hash_without_space_not_heading(self):
        """#hashtag is NOT a markdown heading — should be untouched."""
        text = "#hashtag\n#100things"
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, "#hashtag\n#100things")

    def test_heading_at_end_of_line(self):
        """A lone '#' at end of line IS a valid ATX heading (empty h1)."""
        text = "# "
        result = downlevel_headings(text, levels=2)
        self.assertEqual(result, "### ")

    def test_mixed_content(self):
        """Realistic Claude response with headings, code, and text."""
        text = (
            "Here's my analysis:\n\n"
            "# Overview\n\n"
            "Some text.\n\n"
            "## Details\n\n"
            "```python\n"
            "# This is a Python comment\n"
            "x = 1\n"
            "```\n\n"
            "## Conclusion\n\n"
            "Done."
        )
        result = downlevel_headings(text, levels=2)
        self.assertIn("### Overview", result)
        self.assertIn("#### Details", result)
        self.assertIn("#### Conclusion", result)
        self.assertIn("# This is a Python comment", result)  # preserved in code

    def test_empty_string(self):
        self.assertEqual(downlevel_headings("", levels=2), "")

    def test_custom_levels(self):
        """Can shift by 1 or 3 levels too."""
        self.assertEqual(downlevel_headings("# H1", levels=1), "## H1")
        self.assertEqual(downlevel_headings("# H1", levels=3), "#### H1")

    # -- Adaptive shift (levels=None, the default) --

    def test_adaptive_h1_shifts_by_2(self):
        """Content starting at h1 shifts by 2 (same as old fixed default)."""
        text = "# Title\n## Sub\n### Deep"
        result = downlevel_headings(text)
        self.assertEqual(result, "### Title\n#### Sub\n##### Deep")

    def test_adaptive_h2_shifts_by_1(self):
        """Content starting at h2 shifts by 1 — no gap, h3 follows role h2."""
        text = "## Issues Found\n### Detail\n#### Sub-detail"
        result = downlevel_headings(text)
        self.assertEqual(result, "### Issues Found\n#### Detail\n##### Sub-detail")

    def test_adaptive_h3_no_shift(self):
        """Content starting at h3 or deeper needs no shift."""
        text = "### Already fine\n#### Sub"
        result = downlevel_headings(text)
        self.assertEqual(result, text)

    def test_adaptive_h4_no_shift(self):
        """Content at h4+ passes through unchanged."""
        text = "#### Deep\n##### Deeper"
        result = downlevel_headings(text)
        self.assertEqual(result, text)

    def test_adaptive_no_headings(self):
        """No headings means no shift — text returned unchanged."""
        text = "Just plain text\nwith no headings."
        result = downlevel_headings(text)
        self.assertEqual(result, text)

    def test_adaptive_code_block_headings_ignored(self):
        """Headings inside code blocks don't affect adaptive min detection."""
        text = "```\n# code comment\n```\n## Real heading"
        result = downlevel_headings(text)
        # min_level is 2 (the ## outside code), shift by 1
        self.assertEqual(result, "```\n# code comment\n```\n### Real heading")

    def test_adaptive_preserves_relative_hierarchy(self):
        """Adaptive shift preserves the relative spacing between levels."""
        text = "## Top\ntext\n#### Skip to h4\nmore text"
        result = downlevel_headings(text)
        # min is h2, shift by 1: h2->h3, h4->h5
        self.assertEqual(result, "### Top\ntext\n##### Skip to h4\nmore text")

    def test_adaptive_h6_cap(self):
        """Adaptive still caps at h6."""
        text = "# H1\n###### H6"
        result = downlevel_headings(text)
        # min is h1, shift by 2: h1->h3, h6->min(8,6)=h6
        self.assertEqual(result, "### H1\n###### H6")


class TestEscapeHeadings(unittest.TestCase):
    """Test the escape_headings function (used for user messages)."""

    def test_basic_escape(self):
        """# at line start becomes \\# (literal text, not heading)."""
        self.assertEqual(escape_headings("# comment"), "\\# comment")

    def test_multiple_levels(self):
        """All heading levels are escaped."""
        self.assertEqual(escape_headings("## sub"), "\\## sub")
        self.assertEqual(escape_headings("###### deep"), "\\###### deep")

    def test_preserves_code_blocks(self):
        """# inside code blocks is left alone."""
        text = "```bash\n# shell comment\necho hi\n```"
        self.assertEqual(escape_headings(text), text)

    def test_preserves_tilde_code_blocks(self):
        text = "~~~\n# inside\n~~~"
        self.assertEqual(escape_headings(text), text)

    def test_hash_without_space_not_escaped(self):
        """#hashtag is not a heading pattern — leave it alone."""
        text = "#hashtag\n#100things"
        self.assertEqual(escape_headings(text), text)

    def test_consecutive_shell_comments(self):
        """The original bug #5: shell comments pasted by user."""
        text = (
            "Here\n\n"
            "# Show logs starting from the moment when specified version\n"
            "# was launched for the first time\n\n"
            "I want to use lnav as well"
        )
        result = escape_headings(text)
        self.assertIn("\\# Show logs starting", result)
        self.assertIn("\\# was launched", result)
        self.assertIn("Here", result)
        self.assertIn("I want to use lnav as well", result)

    def test_mixed_text_and_headings(self):
        """Only heading-pattern lines are escaped."""
        text = "plain text\n# heading\nmore text"
        result = escape_headings(text)
        self.assertEqual(result, "plain text\n\\# heading\nmore text")

    def test_empty_string(self):
        self.assertEqual(escape_headings(""), "")

    def test_no_headings(self):
        text = "Just some text\nno headings here"
        self.assertEqual(escape_headings(text), text)


class TestSaveAsMarkdownHeadings(unittest.TestCase):
    """Integration: verify save_as_markdown applies correct heading treatment."""

    def test_assistant_headings_are_downleveled(self):
        """Claude's headings are downleveled, not escaped."""
        conversation = [
            {
                "role": "user",
                "content": "Tell me about X",
                "timestamp": "2026-03-16T12:00:00Z",
            },
            {
                "role": "assistant",
                "content": "# Big Title\n\n## Section\n\nSome text.",
                "timestamp": "2026-03-16T12:01:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = save_as_markdown(
                conversation,
                "test-session-id",
                Path(tmpdir),
                filename_override="test.md",
            )
            content = outpath.read_text()

            # Document structure is preserved
            self.assertTrue(content.startswith("# Claude Conversation Log"))
            self.assertIn("## 👤 User", content)
            self.assertIn("## 🤖 Claude", content)
            # Content headings are pushed to h3+
            self.assertIn("### Big Title", content)
            self.assertIn("#### Section", content)

    def test_user_headings_are_escaped(self):
        """User's # lines are escaped to literal text, not downleveled."""
        conversation = [
            {
                "role": "user",
                "content": "Here\n\n# Show logs\n# for version 1\n\nUse lnav",
                "timestamp": "2026-03-16T12:00:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = save_as_markdown(
                conversation,
                "test-session-id",
                Path(tmpdir),
                filename_override="test_user.md",
            )
            content = outpath.read_text()

            # '#' is escaped — no heading rendered
            self.assertIn("\\# Show logs", content)
            self.assertIn("\\# for version 1", content)
            # NOT downleveled (no ### in user messages)
            self.assertNotIn("### Show logs", content)

    def test_no_content_h1_or_h2_leak(self):
        """Neither user nor assistant content produces rogue h1/h2."""
        conversation = [
            {
                "role": "user",
                "content": "# user heading",
                "timestamp": "2026-03-16T12:00:00Z",
            },
            {
                "role": "assistant",
                "content": "# assistant heading\n\n## sub heading",
                "timestamp": "2026-03-16T12:01:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = save_as_markdown(
                conversation,
                "test-session-id",
                Path(tmpdir),
                filename_override="test_leak.md",
            )
            lines = outpath.read_text().split('\n')
            for line in lines:
                if line.startswith('# ') and 'Claude Conversation Log' not in line:
                    self.fail(f"Content h1 leaked: {line}")
                if (
                    line.startswith('## ')
                    and '👤' not in line
                    and '🤖' not in line
                ):
                    self.fail(f"Content h2 leaked: {line}")

    def test_assistant_h2_start_no_gap(self):
        """When Claude starts at h2, adaptive shift avoids skipping h3."""
        conversation = [
            {
                "role": "assistant",
                "content": "## Issues Found\n\n### Detail\n\nSome text.",
                "timestamp": "2026-03-16T12:01:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = save_as_markdown(
                conversation,
                "test-session-id",
                Path(tmpdir),
                filename_override="test_h2.md",
            )
            content = outpath.read_text()

            # h2 -> h3 (directly under role header), h3 -> h4
            self.assertIn("### Issues Found", content)
            self.assertIn("#### Detail", content)
            # No gap: h3 IS used (unlike old +2 which would produce h4)
            self.assertNotIn("#### Issues Found", content)

    def test_content_leading_whitespace_stripped(self):
        """Leading/trailing newlines in content should be stripped."""
        conversation = [
            {
                "role": "assistant",
                "content": "\n\n\nActual content here\n\n\n",
                "timestamp": "2026-03-16T12:00:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            outpath = save_as_markdown(
                conversation,
                "test-session-id",
                Path(tmpdir),
                filename_override="test_strip.md",
            )
            content = outpath.read_text()
            self.assertNotIn("## 🤖 Claude\n\n\n\n", content)
            self.assertIn("## 🤖 Claude\n\nActual content here", content)


if __name__ == "__main__":
    unittest.main()
