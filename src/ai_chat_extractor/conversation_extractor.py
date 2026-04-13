#!/usr/bin/env python3
"""
Extract clean conversation logs from AI assistant rollout files.

Supports Claude Code (~/.claude/projects/) and OpenAI Codex
(~/.codex/sessions/) via a SourceAdapter registry — the source is
selected with the ``source`` constructor arg or ``--source`` CLI flag.
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import formatters
from .source_adapter import get_source


class ConversationExtractor:
    """Extract and convert AI assistant conversations to markdown/JSON/HTML.

    Delegates the per-source work to a ``SourceAdapter`` looked up by name:
      - ``adapter.parsers``   : JSONL parsing, content extraction
      - ``adapter.metadata``  : session discovery, metadata extraction
      - ``formatters``        : output formatting + filename generation (source-aware)
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        source_dir: Optional[Path] = None,
        source: str = "claude",
    ):
        """Initialize the extractor.

        Args:
            output_dir: Directory to save exported files to.
            source_dir: Override the adapter's default source directory.
                        Useful for reading synced remote logs.
            source: Which source backend to use ("claude" or "codex").
        """
        self.adapter = get_source(source)
        self.source = self.adapter.name

        if source_dir:
            self.session_dir = Path(source_dir)
        else:
            self.session_dir = self.adapter.default_source_dir

        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Try multiple possible output directories
            display = self.adapter.display_name
            possible_dirs = [
                Path.home() / "Desktop" / f"{display} logs",
                Path.home() / "Documents" / f"{display} logs",
                Path.home() / f"{display} logs",
                Path.cwd() / f"{self.adapter.filename_prefix}-logs",
            ]

            for dir_path in possible_dirs:
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    test_file = dir_path / ".test"
                    test_file.touch()
                    test_file.unlink()
                    self.output_dir = dir_path
                    break
                except Exception:
                    continue
            else:
                self.output_dir = Path.cwd() / f"{self.adapter.filename_prefix}-logs"
                self.output_dir.mkdir(exist_ok=True)

        print(f"📁 Saving logs to: {self.output_dir}")

    # ── Session discovery (delegates to adapter.metadata) ────────────

    def find_sessions(
        self, project_path: Optional[str] = None, include_subagents: bool = False
    ) -> List[Path]:
        """Find all JSONL session files, sorted by most recent first."""
        return self.adapter.metadata.find_sessions(
            self.session_dir, project_path, include_subagents
        )

    def find_subagents(self, session_path: Path) -> List[Path]:
        """Find all subagent JSONL files associated with a main conversation."""
        return self.adapter.metadata.find_subagents(session_path)

    def get_subagent_metadata(self, subagent_path: Path) -> Dict:
        """Get metadata for a subagent from its .meta.json file and JSONL content."""
        return self.adapter.metadata.get_subagent_metadata(subagent_path)

    # ── Parsing helpers (delegates to adapter.parsers) ───────────────

    def _is_ide_preamble(self, text: str) -> bool:
        """Check if text is an IDE-generated preamble rather than real user input."""
        return self.adapter.parsers.is_ide_preamble(text)

    def _extract_first_user_text(self, jsonl_path: Path) -> str:
        """Extract the first meaningful user message text from a JSONL file."""
        return self.adapter.parsers.extract_first_user_text(jsonl_path)

    def extract_session_metadata(self, jsonl_path: Path) -> Dict:
        """Extract all available metadata from a conversation JSONL file."""
        return self.adapter.metadata.extract_session_metadata(jsonl_path)

    # ── Filename generation (delegates to formatters module) ─────────

    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to a URL/filename-safe slug."""
        return formatters.slugify(text)

    def _slug_from_metadata(self, meta: Dict) -> str:
        """Derive a filename slug from metadata."""
        return formatters.slug_from_metadata(meta)

    def _resolve_output_path(self, filename: str) -> Optional[Path]:
        """Resolve output path, skipping if file already exists."""
        return formatters.resolve_output_path(self.output_dir, filename)

    def generate_filename(self, session_path: Path, format: str = "markdown") -> str:
        """Generate output filename from conversation metadata."""
        return formatters.generate_filename(session_path, format, source=self.source)

    def generate_subagent_filename(
        self,
        subagent_path: Path,
        parent_metadata: Dict,
        agent_index: int,
        format: str = "markdown",
    ) -> str:
        """Generate output filename for a subagent conversation."""
        return formatters.generate_subagent_filename(
            subagent_path, parent_metadata, agent_index, format, source=self.source
        )

    # ── Conversation extraction (delegates to adapter.parsers) ───────

    def extract_conversation(
        self, jsonl_path: Path, detailed: bool = False
    ) -> List[Dict[str, str]]:
        """Extract conversation messages from a JSONL file."""
        return self.adapter.parsers.extract_conversation(jsonl_path, detailed)

    def _extract_text_content(self, content, detailed: bool = False) -> str:
        """Extract text from content formats used by this source."""
        return self.adapter.parsers.extract_text_content(content, detailed)

    def get_conversation_preview(self, session_path: Path) -> Tuple[str, int]:
        """Get a preview of the conversation's first real user message and message count."""
        return self.adapter.parsers.get_conversation_preview(session_path)

    # ── Save / export (delegates to formatters module) ───────────────

    def save_as_markdown(
        self,
        conversation: List[Dict[str, str]],
        session_id: str,
        session_path: Optional[Path] = None,
        filename_override: Optional[str] = None,
    ) -> Optional[Path]:
        """Save conversation as clean markdown file."""
        return formatters.save_as_markdown(
            conversation, session_id, self.output_dir,
            session_path, filename_override, source=self.source,
        )

    def save_as_json(
        self,
        conversation: List[Dict[str, str]],
        session_id: str,
        session_path: Optional[Path] = None,
        filename_override: Optional[str] = None,
    ) -> Optional[Path]:
        """Save conversation as JSON file."""
        return formatters.save_as_json(
            conversation, session_id, self.output_dir,
            session_path, filename_override, source=self.source,
        )

    def save_as_html(
        self,
        conversation: List[Dict[str, str]],
        session_id: str,
        session_path: Optional[Path] = None,
        filename_override: Optional[str] = None,
    ) -> Optional[Path]:
        """Save conversation as HTML file with syntax highlighting."""
        return formatters.save_as_html(
            conversation, session_id, self.output_dir,
            session_path, filename_override, source=self.source,
        )

    def save_conversation(
        self,
        conversation: List[Dict[str, str]],
        session_id: str,
        format: str = "markdown",
        session_path: Optional[Path] = None,
        filename_override: Optional[str] = None,
    ) -> Optional[Path]:
        """Save conversation in the specified format."""
        return formatters.save_conversation(
            conversation, session_id, self.output_dir, format,
            session_path, filename_override, source=self.source,
        )

    # ── Display ──────────────────────────────────────────────────────

    def display_conversation(self, jsonl_path: Path, detailed: bool = False) -> None:
        """Display a conversation in the terminal with pagination."""
        try:
            messages = self.extract_conversation(jsonl_path, detailed=detailed)

            if not messages:
                print("❌ No messages found in conversation")
                return

            session_id = jsonl_path.stem

            # Clear screen and show header
            print("\033[2J\033[H", end="")
            print("=" * 60)
            print(f"📄 Viewing: {jsonl_path.parent.name}")
            print(f"Session: {session_id[:8]}...")

            first_timestamp = messages[0].get("timestamp", "")
            if first_timestamp:
                try:
                    dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
                    print(f"Date: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception:
                    pass

            print("=" * 60)
            print("↑↓ to scroll • Q to quit • Enter to continue\n")

            lines_shown = 8
            lines_per_page = 30

            assistant_label = f"🤖 {self.adapter.display_name.upper()}:"
            role_labels = {
                "user": ("👤 HUMAN:", "─" * 40),
                "human": ("👤 HUMAN:", "─" * 40),
                "assistant": (assistant_label, "─" * 40),
                "tool_use": ("🔧 TOOL USE:", None),
                "tool_result": ("📤 TOOL RESULT:", None),
                "system": ("ℹ️ SYSTEM:", None),
            }

            for msg in messages:
                role = msg["role"]
                content = msg["content"]

                label, separator = role_labels.get(role, (f"{role.upper()}:", None))
                if separator:
                    print(f"\n{separator}")
                    print(f"{label}")
                    print(f"{separator}")
                else:
                    print(f"\n{label}")

                lines = content.split('\n')
                max_lines_per_msg = 50

                for line in lines[:max_lines_per_msg]:
                    if len(line) > 100:
                        line = line[:97] + "..."
                    print(line)
                    lines_shown += 1

                    if lines_shown >= lines_per_page:
                        response = input("\n[Enter] Continue • [Q] Quit: ").strip().upper()
                        if response == "Q":
                            print("\n👋 Stopped viewing")
                            return
                        print("\033[2J\033[H", end="")
                        lines_shown = 0

                if len(lines) > max_lines_per_msg:
                    print(f"... [{len(lines) - max_lines_per_msg} more lines truncated]")
                    lines_shown += 1

            print("\n" + "=" * 60)
            print("📄 End of conversation")
            print("=" * 60)
            input("\nPress Enter to continue...")

        except Exception as e:
            print(f"❌ Error displaying conversation: {e}")
            input("\nPress Enter to continue...")

    # ── Listing ──────────────────────────────────────────────────────

    def _project_label(self, session: Path, session_meta: Dict) -> str:
        """Return a human-friendly project label for the listing display."""
        return self.adapter.metadata.project_label(session, session_meta)

    def list_recent_sessions(self, limit: Optional[int] = None) -> List[Path]:
        """List recent sessions with details."""
        sessions = self.find_sessions()
        display = self.adapter.display_name

        if not sessions:
            print(f"❌ No {display} sessions found in {self.session_dir}")
            print(f"💡 Make sure you've used {display} and have conversations saved.")
            return []

        print(f"\n📚 Found {len(sessions)} {display} sessions:\n")
        print("=" * 80)

        sessions_to_show = sessions[:limit] if limit else sessions
        for i, session in enumerate(sessions_to_show, 1):
            session_id = session.stem
            modified = datetime.fromtimestamp(session.stat().st_mtime)

            size = session.stat().st_size
            size_kb = size / 1024

            preview, msg_count = self.get_conversation_preview(session)
            session_meta = self.extract_session_metadata(session)
            project = self._project_label(session, session_meta)

            print(f"\n{i}. 📁 {project}")
            if session_meta["custom_title"]:
                print(f"   🏷️  Title: {session_meta['custom_title']}")
            display_id = session_meta.get("sessionId") or session_id
            print(f"   📄 Session: {display_id[:8]}...")
            print(f"   📅 Modified: {modified.strftime('%Y-%m-%d %H:%M')}")
            print(f"   💬 Messages: {msg_count}")
            print(f"   💾 Size: {size_kb:.1f} KB")
            if session_meta["models"]:
                print(f"   🧠 Models: {', '.join(session_meta['models'])}")
            if session_meta["has_subagents"]:
                print(f"   🤖 Subagents: {session_meta['subagent_count']}")
            print(f"   📝 Preview: \"{preview}...\"")
            print(f"   📎 Output: {self.generate_filename(session)}")

        print("\n" + "=" * 80)
        return sessions[:limit]

    # ── Batch extraction ─────────────────────────────────────────────

    def extract_multiple(
        self,
        sessions: List[Path],
        indices: List[int],
        format: str = "markdown",
        detailed: bool = False,
        include_subagents: bool = True,
    ) -> Tuple[int, int]:
        """Extract multiple sessions by index."""
        success = 0
        skipped = 0
        total = len(indices)

        for idx in indices:
            if 0 <= idx < len(sessions):
                session_path = sessions[idx]
                conversation = self.extract_conversation(session_path, detailed=detailed)
                if conversation:
                    output_path = self.save_conversation(
                        conversation,
                        session_path.stem,
                        format=format,
                        session_path=session_path,
                    )
                    if output_path is None:
                        skipped += 1
                        continue

                    success += 1
                    msg_count = len(conversation)
                    print(
                        f"✅ {success}/{total}: {output_path.name} "
                        f"({msg_count} messages)"
                    )

                    # Extract subagent conversations if requested
                    if include_subagents:
                        subagents = self.find_subagents(session_path)
                        if subagents:
                            parent_meta = self.extract_session_metadata(session_path)
                            print(f"   🤖 Found {len(subagents)} subagent(s)")
                            for sa_idx, sa_path in enumerate(subagents, 1):
                                sa_conversation = self.extract_conversation(
                                    sa_path, detailed=detailed
                                )
                                if sa_conversation:
                                    sa_filename = self.generate_subagent_filename(
                                        sa_path, parent_meta, sa_idx, format=format
                                    )
                                    sa_output = self.save_conversation(
                                        sa_conversation,
                                        sa_path.stem,
                                        format=format,
                                        filename_override=sa_filename,
                                    )
                                    if sa_output is None:
                                        skipped += 1
                                        continue
                                    sa_meta = self.get_subagent_metadata(sa_path)
                                    print(
                                        f"   └─ 🤖 Agent {sa_idx}: {sa_output.name} "
                                        f"({len(sa_conversation)} msgs, "
                                        f"type={sa_meta['agentType']})"
                                    )
                else:
                    print(f"⏭️  Skipped session {idx + 1} (no conversation)")
            else:
                print(f"❌ Invalid session number: {idx + 1}")

        if skipped:
            print(f"⏭️  Skipped {skipped} already exported")

        return success, total


# ── CLI ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Extract AI assistant conversations (Claude Code, OpenAI Codex) "
        "to clean markdown, JSON, or HTML files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                       # List Claude sessions
  %(prog)s --list --source codex        # List Codex sessions
  %(prog)s --extract 1                  # Extract the most recent Claude session
  %(prog)s --extract 1 --source codex   # Extract the most recent Codex session
  %(prog)s --extract 1,3,5              # Extract specific sessions
  %(prog)s --recent 5                   # Extract 5 most recent sessions
  %(prog)s --all                        # Extract all sessions
  %(prog)s --output ~/my-logs           # Specify output directory
  %(prog)s --search "python error"      # Search Claude conversations
  %(prog)s --search "CI/CD" --source codex  # Search Codex conversations
  %(prog)s --format json --all          # Export all as JSON
  %(prog)s --format html --extract 1    # Export session 1 as HTML
  %(prog)s --detailed --extract 1       # Include tool use & developer messages
  %(prog)s --source-dir ~/backups/myserver/.claude/projects/ --list  # Remote-synced Claude data
  %(prog)s --source codex --source-dir ~/backups/myserver/.codex/sessions/ --list
        """,
    )
    parser.add_argument("--list", action="store_true", help="List recent sessions")
    parser.add_argument(
        "--extract",
        type=str,
        help="Extract specific session(s) by number (comma-separated)",
    )
    parser.add_argument(
        "--all", "--logs", action="store_true", help="Extract all sessions"
    )
    parser.add_argument(
        "--recent", type=int, help="Extract N most recent sessions", default=0
    )
    parser.add_argument(
        "--output", type=str, help="Output directory for markdown files"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit for --list command (default: show all)",
        default=None,
    )
    parser.add_argument(
        "--interactive",
        "-i",
        "--start",
        "-s",
        action="store_true",
        help="Launch interactive UI for easy extraction",
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Export mode: 'logs' for interactive UI",
    )

    # Search arguments
    parser.add_argument(
        "--search", type=str, help="Search conversations for text (smart search)"
    )
    parser.add_argument(
        "--search-regex", type=str, help="Search conversations using regex pattern"
    )
    parser.add_argument(
        "--search-date-from", type=str, help="Filter search from date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--search-date-to", type=str, help="Filter search to date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--search-speaker",
        choices=["human", "assistant", "both"],
        default="both",
        help="Filter search by speaker",
    )
    parser.add_argument(
        "--case-sensitive", action="store_true", help="Make search case-sensitive"
    )

    # Export format arguments
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format for exported conversations (default: markdown)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Include tool use, MCP responses, and system messages in export",
    )
    parser.add_argument(
        "--no-subagents",
        action="store_true",
        help="Exclude subagent (task) conversations from extraction",
    )
    parser.add_argument(
        "--source",
        choices=["claude", "codex"],
        default=None,
        help="Which AI assistant's conversations to read. "
        "'claude' reads ~/.claude/projects/; 'codex' reads ~/.codex/sessions/. "
        "Defaults to 'claude' for non-interactive commands; "
        "interactive mode prompts for the source when omitted.",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        help="Override the default source directory for the selected --source. "
        "Use this to extract from a synced remote backup, e.g. "
        "~/backups/myserver/.claude/projects/ or "
        "~/backups/myserver/.codex/sessions/",
    )

    args = parser.parse_args()

    # Handle interactive mode
    if args.interactive or (args.export and args.export.lower() == "logs"):
        from .interactive_ui import main as interactive_main

        interactive_main(source=args.source)
        return

    # Non-interactive commands fall back to Claude when --source is omitted.
    source = args.source or "claude"

    # Initialize extractor with optional output/source directories
    extractor = ConversationExtractor(
        args.output, source_dir=args.source_dir, source=source,
    )

    # Handle search mode
    if args.search or args.search_regex:
        from .search_conversations import ConversationSearcher

        searcher = ConversationSearcher(source=source)

        # Determine search mode and query
        if args.search_regex:
            query = args.search_regex
            mode = "regex"
        else:
            query = args.search
            mode = "smart"

        # Parse date filters
        date_from = None
        date_to = None
        if args.search_date_from:
            try:
                date_from = datetime.strptime(args.search_date_from, "%Y-%m-%d")
            except ValueError:
                print(f"❌ Invalid date format: {args.search_date_from}")
                return

        if args.search_date_to:
            try:
                date_to = datetime.strptime(args.search_date_to, "%Y-%m-%d")
            except ValueError:
                print(f"❌ Invalid date format: {args.search_date_to}")
                return

        # Speaker filter
        speaker_filter = None if args.search_speaker == "both" else args.search_speaker

        # Perform search
        print(f"🔍 Searching for: {query}")
        results = searcher.search(
            query=query,
            mode=mode,
            date_from=date_from,
            date_to=date_to,
            speaker_filter=speaker_filter,
            case_sensitive=args.case_sensitive,
            max_results=30,
        )

        if not results:
            print("❌ No matches found.")
            return

        print(f"\n✅ Found {len(results)} matches across conversations:")

        # Group and display results
        results_by_file = {}
        for result in results:
            if result.file_path not in results_by_file:
                results_by_file[result.file_path] = []
            results_by_file[result.file_path].append(result)

        # Store file paths for potential viewing
        file_paths_list = []
        for file_path, file_results in results_by_file.items():
            file_paths_list.append(file_path)
            print(
                f"\n{len(file_paths_list)}. 📄 {file_path.parent.name} "
                f"({len(file_results)} matches)"
            )
            first = file_results[0]
            print(f"   {first.speaker}: {first.matched_content[:100]}...")

        # Offer to view conversations
        if file_paths_list:
            print("\n" + "=" * 60)
            try:
                view_choice = input(
                    "\nView a conversation? Enter number (1-{}) or press Enter to skip: ".format(
                        len(file_paths_list)
                    )
                ).strip()

                if view_choice.isdigit():
                    view_num = int(view_choice)
                    if 1 <= view_num <= len(file_paths_list):
                        selected_path = file_paths_list[view_num - 1]
                        extractor.display_conversation(selected_path, detailed=args.detailed)

                        extract_choice = (
                            input("\n📤 Extract this conversation? (y/N): ").strip().lower()
                        )
                        if extract_choice == "y":
                            conversation = extractor.extract_conversation(
                                selected_path, detailed=args.detailed
                            )
                            if conversation:
                                session_id = selected_path.stem
                                output = extractor.save_conversation(
                                    conversation,
                                    session_id,
                                    format=args.format,
                                    session_path=selected_path,
                                )
                                if output:
                                    print(f"✅ Saved: {output.name}")
                                else:
                                    print("⏭️  Already exported, skipping")
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Cancelled")

        return

    # Default action is to list sessions
    if args.list or (
        not args.extract
        and not args.all
        and not args.recent
        and not args.search
        and not args.search_regex
    ):
        sessions = extractor.list_recent_sessions(args.limit)

        if sessions and not args.list:
            print("\nTo extract conversations:")
            print("  ai-extract --extract <number>      # Extract specific session")
            print("  ai-extract --recent 5              # Extract 5 most recent")
            print("  ai-extract --all                   # Extract all sessions")

    elif args.extract:
        sessions = extractor.find_sessions()

        # Parse comma-separated indices
        indices = []
        for num in args.extract.split(","):
            try:
                idx = int(num.strip()) - 1
                indices.append(idx)
            except ValueError:
                print(f"❌ Invalid session number: {num}")
                continue

        if indices:
            print(f"\n📤 Extracting {len(indices)} session(s) as {args.format.upper()}...")
            if args.detailed:
                print("📋 Including detailed tool use and system messages")
            if args.no_subagents:
                print("⏭️  Excluding subagent conversations")
            success, total = extractor.extract_multiple(
                sessions,
                indices,
                format=args.format,
                detailed=args.detailed,
                include_subagents=not args.no_subagents,
            )
            print(f"\n✅ Successfully extracted {success}/{total} sessions")

    elif args.recent:
        sessions = extractor.find_sessions()
        limit = min(args.recent, len(sessions))
        print(f"\n📤 Extracting {limit} most recent sessions as {args.format.upper()}...")
        if args.detailed:
            print("📋 Including detailed tool use and system messages")
        if args.no_subagents:
            print("⏭️  Excluding subagent conversations")

        indices = list(range(limit))
        success, total = extractor.extract_multiple(
            sessions,
            indices,
            format=args.format,
            detailed=args.detailed,
            include_subagents=not args.no_subagents,
        )
        print(f"\n✅ Successfully extracted {success}/{total} sessions")

    elif args.all:
        sessions = extractor.find_sessions()
        print(f"\n📤 Extracting all {len(sessions)} sessions as {args.format.upper()}...")
        if args.detailed:
            print("📋 Including detailed tool use and system messages")
        if args.no_subagents:
            print("⏭️  Excluding subagent conversations")

        indices = list(range(len(sessions)))
        success, total = extractor.extract_multiple(
            sessions,
            indices,
            format=args.format,
            detailed=args.detailed,
            include_subagents=not args.no_subagents,
        )
        print(f"\n✅ Successfully extracted {success}/{total} sessions")


def launch_interactive():
    """Launch the interactive UI directly, or handle search if specified."""
    import sys

    # If no arguments provided, launch interactive UI
    if len(sys.argv) == 1:
        from .interactive_ui import main as interactive_main
        interactive_main()
    # Check if 'search' was passed as an argument
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        # Launch real-time search with viewing capability
        from .realtime_search import RealTimeSearch, create_smart_searcher
        from .search_conversations import ConversationSearcher

        extractor = ConversationExtractor()
        searcher = ConversationSearcher()
        smart_searcher = create_smart_searcher(searcher)

        rts = RealTimeSearch(smart_searcher, extractor)
        selected_file = rts.run()

        if selected_file:
            extractor.display_conversation(selected_file)

            try:
                extract_choice = (
                    input("\n📤 Extract this conversation? (y/N): ").strip().lower()
                )
                if extract_choice == "y":
                    conversation = extractor.extract_conversation(selected_file)
                    if conversation:
                        session_id = selected_file.stem
                        output = extractor.save_as_markdown(
                            conversation, session_id, session_path=selected_file
                        )
                        if output:
                            print(f"✅ Saved: {output.name}")
                        else:
                            print("⏭️  Already exported, skipping")
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Cancelled")
    else:
        # If other arguments are provided, run the normal CLI
        main()


if __name__ == "__main__":
    main()
