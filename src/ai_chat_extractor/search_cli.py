#!/usr/bin/env python3
"""
Simple CLI search for AI assistant conversations without terminal control.
This is used when running `ai-search` from the command line.
"""

import argparse

from .search_conversations import ConversationSearcher
from .realtime_search import create_smart_searcher
from .conversation_extractor import ConversationExtractor


def main():
    """Main entry point for CLI search."""
    parser = argparse.ArgumentParser(
        prog="ai-search",
        description="Search AI assistant conversations (Claude Code / OpenAI Codex).",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Search term (words joined with spaces). Prompted if omitted.",
    )
    parser.add_argument(
        "--source",
        choices=["claude", "codex"],
        default="claude",
        help="Which AI assistant's conversations to search (default: claude).",
    )
    args = parser.parse_args()

    if args.query:
        search_term = " ".join(args.query)
    else:
        try:
            search_term = input("🔍 Enter search term: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Search cancelled")
            return

    if not search_term:
        print("❌ No search term provided")
        return

    print(f"\n🔍 Searching for: '{search_term}'")
    print("=" * 60)

    searcher = ConversationSearcher(source=args.source)
    smart_searcher = create_smart_searcher(searcher)

    results = smart_searcher.search(search_term, max_results=20)

    if results:
        print(f"\n✅ Found {len(results)} results across conversations:\n")

        # Group by file
        by_file = {}
        for result in results:
            fname = result.file_path.name
            if fname not in by_file:
                by_file[fname] = []
            by_file[fname].append(result)

        # Display results
        sessions = []
        session_paths = []
        extractor = ConversationExtractor(source=args.source)
        all_sessions = extractor.find_sessions()

        for i, (fname, file_results) in enumerate(by_file.items(), 1):
            stem_id = fname.replace('.jsonl', '')

            matching_path = None
            for session_path in all_sessions:
                if session_path.name == fname:
                    matching_path = session_path
                    session_paths.append(session_path)
                    break

            if matching_path is not None:
                session_meta = extractor.adapter.metadata.extract_session_metadata(
                    matching_path
                )
                display_id = session_meta.get("sessionId") or stem_id
            else:
                display_id = stem_id

            sessions.append((fname, display_id))
            print(f"{i}. Session {display_id[:8]}... ({len(file_results)} matches)")

            # Show first match preview
            first = file_results[0]
            preview = first.matched_content[:150].replace('\n', ' ')
            print(f"   {first.speaker}: {preview}...")
            print()

        # Offer to view or extract conversations
        if session_paths:
            print("\n" + "=" * 60)
            print("Options:")
            print("  V. VIEW a conversation")
            print("  E. EXTRACT all conversations")
            print("  Q. QUIT")

            try:
                choice = input("\nYour choice: ").strip().upper()

                if choice == 'V':
                    # View conversation
                    extract_prompt = "\n📤 Extract this conversation? (y/N): "
                    if len(session_paths) == 1:
                        extractor.display_conversation(session_paths[0])

                        extract_choice = input(extract_prompt).strip().lower()
                        if extract_choice == 'y':
                            conversation = extractor.extract_conversation(session_paths[0])
                            if conversation:
                                output = extractor.save_as_markdown(
                                    conversation, sessions[0][1]
                                )
                                if output:
                                    print(f"✅ Saved: {output.name}")
                                else:
                                    print("⏭️  Already exported, skipping")
                    else:
                        print("\nSelect conversation to view:")
                        for i, (fname, sid) in enumerate(sessions, 1):
                            print(f"  {i}. {sid[:8]}...")

                        try:
                            view_num = int(input(
                                "\nEnter number (1-{}): ".format(len(sessions))
                            ))
                            if 1 <= view_num <= len(session_paths):
                                chosen_path = session_paths[view_num - 1]
                                chosen_sid = sessions[view_num - 1][1]
                                extractor.display_conversation(chosen_path)

                                extract_choice = input(extract_prompt).strip().lower()
                                if extract_choice == 'y':
                                    conversation = extractor.extract_conversation(
                                        chosen_path
                                    )
                                    if conversation:
                                        output = extractor.save_as_markdown(
                                            conversation, chosen_sid
                                        )
                                        if output:
                                            print(f"✅ Saved: {output.name}")
                                        else:
                                            print("⏭️  Already exported, skipping")
                        except (ValueError, IndexError):
                            print("❌ Invalid selection")

                elif choice == 'E':
                    for i, (session_path, (fname, sid)) in enumerate(
                        zip(session_paths, sessions), 1
                    ):
                        print(f"\n📤 Extracting session {i}...")
                        conversation = extractor.extract_conversation(session_path)
                        if conversation:
                            output = extractor.save_as_markdown(conversation, sid)
                            if output:
                                print(f"✅ Saved: {output.name}")
                            else:
                                print("⏭️  Already exported, skipping")

                elif choice == 'Q':
                    print("\n👋 Goodbye!")

            except (EOFError, KeyboardInterrupt):
                print("\n👋 Search cancelled")
    else:
        print(f"\n❌ No matches found for '{search_term}'")
        print("\n💡 Tips:")
        print("   - Try a more general search term")
        print("   - Search is case-insensitive by default")
        print("   - Partial matches are included")


if __name__ == "__main__":
    main()
