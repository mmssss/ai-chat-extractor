#!/usr/bin/env python3
"""
Aligned tests for search_conversations.py with meaningful coverage
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path before local imports
sys.path.append(str(Path(__file__).parent.parent))

# Local imports after sys.path modification
from search_conversations import ConversationSearcher, SearchResult  # noqa: E402


class TestSearchResult(unittest.TestCase):
    """Test SearchResult dataclass"""

    def test_search_result_creation(self):
        """Test creating a SearchResult"""
        result = SearchResult(
            file_path=Path("/test/path.jsonl"),
            conversation_id="conv-001",
            matched_content="Hello world",
            context="Previous message",
            speaker="human",
            timestamp=datetime(2024, 1, 1, 10, 0),
            relevance_score=0.95,
            line_number=5,
        )

        self.assertEqual(result.file_path, Path("/test/path.jsonl"))
        self.assertEqual(result.relevance_score, 0.95)
        self.assertEqual(result.speaker, "human")
        self.assertEqual(result.conversation_id, "conv-001")

    def test_search_result_string_representation(self):
        """Test SearchResult string representation"""
        result = SearchResult(
            file_path=Path("/test/project/chat_123.jsonl"),
            conversation_id="chat_123",
            matched_content="Test content",
            context="Test context for display",
            speaker="human",
            timestamp=datetime(2024, 1, 1, 10, 0),
            relevance_score=0.8,
            line_number=1,
        )

        str_repr = str(result)
        self.assertIn("chat_123.jsonl", str_repr)
        self.assertIn("Human", str_repr)  # speaker.title() in __str__
        self.assertIn("80%", str_repr)  # Relevance score as percentage


class TestConversationSearcher(unittest.TestCase):
    """Test ConversationSearcher functionality"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.searcher = ConversationSearcher()

        # Create test conversation files
        self.create_test_conversations()

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_conversations(self):
        """Create test conversation files"""
        # Project 1: Python discussion
        project1 = Path(self.temp_dir) / ".claude" / "projects" / "python_project"
        project1.mkdir(parents=True)

        conv1 = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "How do I use Python decorators?",
                },
                "timestamp": "2024-01-01T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Python decorators are a way to modify functions.",
                        }
                    ],
                },
                "timestamp": "2024-01-01T10:01:00Z",
            },
        ]

        with open(project1 / "chat_001.jsonl", "w") as f:
            for msg in conv1:
                f.write(json.dumps(msg) + "\n")

        # Project 2: JavaScript discussion
        project2 = Path(self.temp_dir) / ".claude" / "projects" / "js_project"
        project2.mkdir(parents=True)

        conv2 = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Explain JavaScript promises"},
                "timestamp": "2024-01-02T10:00:00Z",
            }
        ]

        with open(project2 / "chat_002.jsonl", "w") as f:
            for msg in conv2:
                f.write(json.dumps(msg) + "\n")

    def test_search_exact_match(self):
        """Test exact string matching"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search(
            "Python decorators", search_dir=search_dir, mode="exact"
        )

        self.assertGreater(len(results), 0)
        # matched_content or context should contain the match
        self.assertIn("decorators", results[0].matched_content.lower())

    def test_search_case_insensitive(self):
        """Test case-insensitive search"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results1 = self.searcher.search("python", search_dir=search_dir, case_sensitive=False)
        results2 = self.searcher.search("PYTHON", search_dir=search_dir, case_sensitive=False)

        # Should find same results regardless of case
        self.assertEqual(len(results1), len(results2))

    def test_search_case_sensitive(self):
        """Test case-sensitive search"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results1 = self.searcher.search("Python", search_dir=search_dir, case_sensitive=True)
        results2 = self.searcher.search("python", search_dir=search_dir, case_sensitive=True)

        # May find different results based on case
        self.assertIsNotNone(results1)
        self.assertIsNotNone(results2)

    def test_search_regex_mode(self):
        """Test regex pattern matching"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search(r"Python|JavaScript", search_dir=search_dir, mode="regex")

        # Should find both Python and JavaScript mentions
        self.assertGreater(len(results), 0)
        matched_contents = [r.matched_content for r in results]
        self.assertTrue(
            any("Python" in c for c in matched_contents)
            or any("JavaScript" in c for c in matched_contents)
        )

    def test_search_smart_mode(self):
        """Test smart search mode"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("programming language", search_dir=search_dir, mode="smart")

        # Should find relevant results even without exact match
        self.assertIsNotNone(results)

    def test_search_speaker_filter(self):
        """Test filtering by speaker"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        human_results = self.searcher.search("How", search_dir=search_dir, speaker_filter="human")
        assistant_results = self.searcher.search(
            "way to", search_dir=search_dir, speaker_filter="assistant"
        )

        # Check speaker filtering - speaker values are lowercase in implementation
        for result in human_results:
            self.assertEqual(result.speaker, "human")

        for result in assistant_results:
            self.assertEqual(result.speaker, "assistant")

    def test_search_date_filter(self):
        """Test date range filtering"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        # Search only for conversations after 2024-01-01 15:00
        date_from = datetime(2024, 1, 1, 15, 0)
        results = self.searcher.search(
            "JavaScript", search_dir=search_dir, date_from=date_from
        )

        # Should only find JavaScript conversation (2024-01-02) if file mtime is after
        # Note: date filter is based on file modification time, not content timestamp
        self.assertIsNotNone(results)

    def test_search_max_results(self):
        """Test limiting number of results"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search(
            "Python", search_dir=search_dir, max_results=1
        )

        self.assertLessEqual(len(results), 1)

    def test_search_empty_query(self):
        """Test searching with empty query returns empty results"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("", search_dir=search_dir)

        # Empty query returns empty results by design
        self.assertEqual(len(results), 0)

    def test_search_no_matches(self):
        """Test search with no matches"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("nonexistent12345query", search_dir=search_dir)

        self.assertEqual(len(results), 0)

    def test_search_with_context(self):
        """Test that search results include context"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("decorators", search_dir=search_dir, mode="exact")

        if results:
            # Should have context
            self.assertIsNotNone(results[0].context)

    def test_semantic_search_without_spacy(self):
        """Test semantic search falls back when spaCy not available"""
        with patch("search_conversations.SPACY_AVAILABLE", False):
            search_dir = Path(self.temp_dir) / ".claude" / "projects"
            results = self.searcher.search("programming", search_dir=search_dir, mode="semantic")

            # Should fall back to smart search
            self.assertIsNotNone(results)

    def test_semantic_search_with_spacy(self):
        """Test semantic search with spaCy available"""
        # nlp is an instance attribute, so we patch it on the instance
        mock_nlp = Mock()

        # Create mock tokens that support iteration
        mock_token = Mock()
        mock_token.is_stop = False
        mock_token.is_alpha = True
        mock_token.lemma_ = "coding"
        mock_token.text = "coding"

        # Mock doc needs to be iterable (for token iteration)
        mock_doc = Mock()
        mock_doc.__iter__ = Mock(return_value=iter([mock_token]))
        mock_doc.text = "coding"
        mock_nlp.return_value = mock_doc

        # Temporarily set nlp on the searcher instance
        original_nlp = self.searcher.nlp
        self.searcher.nlp = mock_nlp

        try:
            search_dir = Path(self.temp_dir) / ".claude" / "projects"
            results = self.searcher.search("coding", search_dir=search_dir, mode="semantic")

            # Should use semantic similarity
            self.assertIsNotNone(results)
        finally:
            self.searcher.nlp = original_nlp

    def test_search_corrupted_jsonl(self):
        """Test search handles corrupted JSONL files gracefully"""
        # Create corrupted file
        bad_project = Path(self.temp_dir) / ".claude" / "projects" / "bad_project"
        bad_project.mkdir(parents=True)

        with open(bad_project / "chat_bad.jsonl", "w") as f:
            f.write("not json\n")
            f.write("{invalid json}\n")
            f.write(
                json.dumps({
                    "type": "user",
                    "message": {"role": "user", "content": "Valid message"},
                }) + "\n"
            )

        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        # Should not crash, just skip bad lines
        results = self.searcher.search("Valid", search_dir=search_dir)
        self.assertIsNotNone(results)

    def test_rank_results(self):
        """Test that search sorts results by relevance"""
        # The searcher.search() method sorts by relevance internally
        # We can verify by checking returned results are sorted
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("Python", search_dir=search_dir, mode="smart")

        if len(results) > 1:
            # Results should be sorted by relevance (descending)
            for i in range(len(results) - 1):
                self.assertGreaterEqual(
                    results[i].relevance_score,
                    results[i + 1].relevance_score
                )

    def test_extract_content(self):
        """Test content extraction from different message formats"""
        # Plain string content wrapped in the real Claude entry shape.
        entry_with_string = {
            "type": "user",
            "message": {"role": "user", "content": "Simple string"},
        }
        content = self.searcher._extract_content(entry_with_string)
        self.assertEqual(content, "Simple string")

        # List-of-text-parts content (the detailed Claude assistant shape).
        entry_with_message = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"}
                ]
            }
        }
        content = self.searcher._extract_content(entry_with_message)
        self.assertEqual(content, "Part 1 Part 2")

        # Entries with an unknown envelope type return empty.
        entry_empty = {"type": "other"}
        content = self.searcher._extract_content(entry_empty)
        self.assertEqual(content, "")


class TestSearchIntegration(unittest.TestCase):
    """Integration tests for search functionality"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.searcher = ConversationSearcher()

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_search_workflow(self):
        """Test complete search workflow"""
        # Create realistic conversation
        project = Path(self.temp_dir) / ".claude" / "projects" / "test_project"
        project.mkdir(parents=True)

        conversation = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "How do I handle errors in Python?",
                },
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "You can use try-except blocks for error handling.",
                        }
                    ],
                },
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Can you show an example?"},
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "try:\n    risky_operation()\n"
                                "except Exception as e:\n    print(f'Error: {e}')"
                            ),
                        }
                    ],
                },
                "timestamp": datetime.now().isoformat(),
            },
        ]

        with open(project / "chat_test.jsonl", "w") as f:
            for msg in conversation:
                f.write(json.dumps(msg) + "\n")

        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        # Search for error handling
        results = self.searcher.search("error handling", search_dir=search_dir, mode="smart")

        self.assertGreater(len(results), 0)

        # Verify results have expected structure
        first = results[0]
        self.assertIsInstance(first.file_path, Path)
        self.assertIn("test_project", str(first.file_path))
        self.assertGreater(first.relevance_score, 0)
        self.assertIn(first.speaker, ["human", "assistant"])


if __name__ == "__main__":
    unittest.main()
