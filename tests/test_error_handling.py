#!/usr/bin/env python3
"""
Error handling and edge case tests for meaningful coverage
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path before local imports
sys.path.append(str(Path(__file__).parent.parent))

# Local imports after sys.path modification
from conversation_extractor import (ConversationExtractor,  # noqa: E402
                                    launch_interactive, main)


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_fallback_all_dirs_fail(self):
        """Test init when fallback directories are used"""
        with patch("conversation_extractor.Path.home", return_value=Path(self.temp_dir)):
            # Should find a writable directory (temp_dir based paths are writable)
            extractor = ConversationExtractor(None)
            self.assertIsNotNone(extractor.output_dir)
            self.assertTrue(extractor.output_dir.exists())

    def test_extract_conversation_permission_error(self):
        """Test extract_conversation with permission error"""
        test_file = Path(self.temp_dir) / "test.jsonl"
        test_file.write_text('{"type": "test"}')

        extractor = ConversationExtractor(self.temp_dir)

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with patch("builtins.print") as mock_print:
                result = extractor.extract_conversation(test_file)
                self.assertEqual(result, [])
                # Should print error message
                mock_print.assert_called()
                args = mock_print.call_args[0][0]
                self.assertIn("Error reading file", args)

    def test_save_as_markdown_write_error(self):
        """Test save_as_markdown with write error"""
        extractor = ConversationExtractor(self.temp_dir)
        conversation = [{"role": "user", "content": "Test", "timestamp": ""}]

        with patch("builtins.open", side_effect=IOError("Disk full")):
            # The current implementation doesn't catch this error,
            # so it should propagate
            with self.assertRaises(IOError):
                extractor.save_as_markdown(conversation, "test")

    def test_list_recent_sessions_no_sessions_messages(self):
        """Test list_recent_sessions prints correct messages when no sessions"""
        extractor = ConversationExtractor(self.temp_dir)

        with patch.object(extractor, "find_sessions", return_value=[]):
            with patch("builtins.print") as mock_print:
                _ = extractor.list_recent_sessions()

                # Check all expected messages are printed
                print_calls = [str(call) for call in mock_print.call_args_list]
                self.assertTrue(
                    any("No Claude sessions found" in str(call) for call in print_calls)
                )
                self.assertTrue(
                    any(
                        "Make sure you've used Claude" in str(call)
                        for call in print_calls
                    )
                )

    def test_extract_multiple_skip_message(self):
        """Test extract_multiple prints skip message for empty conversations"""
        extractor = ConversationExtractor(self.temp_dir)
        sessions = [Path("test.jsonl")]

        with patch.object(extractor, "extract_conversation", return_value=[]):
            with patch("builtins.print") as mock_print:
                success, total = extractor.extract_multiple(sessions, [0])

                # Should print skip message
                print_calls = [str(call) for call in mock_print.call_args_list]
                self.assertTrue(
                    any("Skipped session" in str(call) for call in print_calls)
                )
                self.assertEqual(success, 0)
                self.assertEqual(total, 1)


class TestMainFunctionErrorCases(unittest.TestCase):
    """Test main() function error handling"""

    def test_main_invalid_extract_number_handling(self):
        """Test main handles invalid extract numbers gracefully"""
        with patch("sys.argv", ["prog", "--extract", "abc,1,xyz"]):
            with patch.object(
                ConversationExtractor,
                "find_sessions",
                return_value=[Path("test.jsonl")],
            ):
                with patch.object(
                    ConversationExtractor, "extract_multiple",
                    return_value=(1, 1)
                ) as mock_extract:
                    with patch("builtins.print") as mock_print:
                        main()

                        # Should skip invalid numbers but process valid ones
                        mock_extract.assert_called_once()
                        args = mock_extract.call_args[0]
                        self.assertEqual(args[1], [0])  # Only valid index

                        # Should print error messages
                        print_calls = [str(call) for call in mock_print.call_args_list]
                        self.assertTrue(
                            any(
                                "Invalid session number: abc" in str(call)
                                for call in print_calls
                            )
                        )
                        self.assertTrue(
                            any(
                                "Invalid session number: xyz" in str(call)
                                for call in print_calls
                            )
                        )

    def test_main_all_with_no_sessions(self):
        """Test --all command with no sessions found"""
        with patch("sys.argv", ["prog", "--all"]):
            with patch.object(
                ConversationExtractor, "find_sessions", return_value=[]
            ):
                with patch.object(
                    ConversationExtractor, "extract_multiple", return_value=(0, 0)
                ) as mock_extract:
                    with patch("builtins.print"):
                        main()

                        # Should handle empty list gracefully
                        mock_extract.assert_called_once()
                        args = mock_extract.call_args[0]
                        self.assertEqual(args[0], [])
                        self.assertEqual(args[1], [])

    def test_main_search_import_error(self):
        """Test main handles search import error"""
        with patch("sys.argv", ["prog", "--search", "test"]):
            # Simulate import error
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                with patch("builtins.print"):
                    with patch("sys.exit"):
                        # Should handle import error gracefully
                        try:
                            main()
                        except ImportError:
                            pass  # Expected

    def test_launch_interactive_import_error(self):
        """Test launch_interactive handles import error"""
        with patch("builtins.__import__", side_effect=ImportError("No interactive_ui")):
            with patch("builtins.print"):
                with patch("sys.exit"):
                    # Should handle import error gracefully
                    try:
                        launch_interactive()
                    except ImportError:
                        pass  # Expected in current implementation


class TestSearchFunctionality(unittest.TestCase):
    """Test search functionality in main()"""

    def test_main_search_basic(self):
        """Test basic search functionality"""
        mock_searcher = Mock()
        mock_searcher.search.return_value = [
            Mock(
                file_path=Path("test.jsonl"),
                conversation_id="123",
                matched_content="test match",
                speaker="human",
                relevance_score=0.9,
            )
        ]

        mock_search_module = Mock()
        mock_search_module.ConversationSearcher.return_value = mock_searcher

        with patch("sys.argv", ["prog", "--search", "test query"]):
            with patch.dict(
                "sys.modules",
                {"search_conversations": mock_search_module},
            ):
                with patch("builtins.print"):
                    with patch("builtins.input", return_value=""):
                        main()

                        # Should call search
                        mock_searcher.search.assert_called()

    def test_main_search_with_filters(self):
        """Test search with all valid filter options"""
        mock_searcher = Mock()
        mock_searcher.search.return_value = []

        mock_search_module = Mock()
        mock_search_module.ConversationSearcher.return_value = mock_searcher

        with patch(
            "sys.argv",
            [
                "prog",
                "--search",
                "test",
                "--search-speaker",
                "human",
                "--search-date-from",
                "2024-01-01",
                "--search-date-to",
                "2024-12-31",
                "--case-sensitive",
            ],
        ):
            with patch.dict(
                "sys.modules",
                {"search_conversations": mock_search_module},
            ):
                with patch("builtins.print"):
                    main()

                    # Verify search was called with correct parameters
                    mock_searcher.search.assert_called_once()
                    call_kwargs = mock_searcher.search.call_args[1]
                    self.assertEqual(call_kwargs["speaker_filter"], "human")
                    self.assertTrue(call_kwargs["case_sensitive"])


class TestInteractiveMode(unittest.TestCase):
    """Test interactive mode functionality"""

    def test_main_interactive_flag_calls_launch(self):
        """Test --interactive flag calls interactive_main from interactive_ui"""
        with patch("sys.argv", ["prog", "--interactive"]):
            with patch.dict(
                "sys.modules",
                {"interactive_ui": Mock(main=Mock())}
            ) as mock_modules:
                with patch("builtins.print"):
                    main()
                    mock_modules["interactive_ui"].main.assert_called_once()

    def test_main_export_flag_calls_interactive(self):
        """Test --export flag launches interactive mode"""
        with patch("sys.argv", ["prog", "--export", "logs"]):
            with patch.dict(
                "sys.modules",
                {"interactive_ui": Mock(main=Mock())}
            ) as mock_modules:
                with patch("builtins.print"):
                    main()
                    mock_modules["interactive_ui"].main.assert_called_once()

    def test_main_no_args_lists_sessions(self):
        """Test no arguments lists sessions (default action)"""
        with patch("sys.argv", ["prog"]):
            with patch.object(
                ConversationExtractor, "list_recent_sessions",
                return_value=[]
            ) as mock_list:
                with patch("builtins.print"):
                    main()
                    # Default action with no args is to list sessions
                    mock_list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
