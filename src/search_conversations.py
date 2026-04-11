#!/usr/bin/env python3
"""
Search functionality for AI Chat Extractor

This module provides powerful search capabilities including:
- Full-text search with relevance ranking
- Regex pattern matching
- Date range filtering
- Speaker filtering (Human/Assistant)
- Semantic search using NLP

Adapted from CAKE's conversation parser for Claude conversation search.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from .source_adapter import get_source
except ImportError:
    from source_adapter import get_source

# Optional NLP imports for semantic search
try:
    import spacy

    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    print("Note: Install spacy for enhanced semantic search capabilities")
    print("      pip install spacy && python -m spacy download en_core_web_sm")


@dataclass
class SearchResult:
    """Represents a search result with context"""

    file_path: Path
    conversation_id: str
    matched_content: str
    context: str  # Surrounding text for context
    speaker: str  # 'human' or 'assistant'
    timestamp: Optional[datetime] = None
    relevance_score: float = 0.0
    line_number: int = 0

    def __str__(self) -> str:
        """User-friendly string representation"""
        return (
            f"\n{'=' * 60}\n"
            f"File: {self.file_path.name}\n"
            f"Speaker: {self.speaker.title()}\n"
            f"Relevance: {self.relevance_score:.0%}\n"
            f"{'=' * 60}\n"
            f"{self.context}\n"
        )


class ConversationSearcher:
    """
    Main search engine for AI assistant conversations.

    Provides multiple search modes and intelligent ranking. Source-agnostic:
    dispatches per-entry parsing through the configured SourceAdapter so the
    same search/rank/context code works for Claude, Codex, and future sources.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        search_dir: Optional[Path] = None,
        source: str = "claude",
    ):
        """
        Initialize the searcher.

        Args:
            cache_dir: Optional cache directory (defaults to adapter's cache_subdir)
            search_dir: Optional search root (defaults to adapter's default_source_dir)
            source: Which source adapter to use ("claude" or "codex")
        """
        self.source = source
        self.adapter = get_source(source)
        self.cache_dir = cache_dir or self.adapter.cache_subdir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.search_dir = search_dir or self.adapter.default_source_dir

        # Initialize NLP if available
        self.nlp = None
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                # Disable unnecessary components for speed
                self.nlp.select_pipes(disable=["ner", "lemmatizer"])
            except Exception:
                print("Warning: spaCy model not found. Using basic search.")

        # Common words to ignore in relevance scoring
        self.stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "i", "you", "we", "they",
            "it", "this", "that", "these", "those",
        }

    # ── Public API ───────────────────────────────────────────────────

    def search(
        self,
        query: str,
        search_dir: Optional[Path] = None,
        mode: str = "smart",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        speaker_filter: Optional[str] = None,
        max_results: int = 20,
        case_sensitive: bool = False,
    ) -> List[SearchResult]:
        """
        Search conversations with various filters.

        Args:
            query: Search query (text or regex pattern)
            search_dir: Directory to search in (default: ~/.claude/projects)
            mode: Search mode - "smart", "exact", "regex", "semantic"
            date_from: Filter results from this date
            date_to: Filter results until this date
            speaker_filter: Filter by speaker - "human", "assistant", or None for both
            max_results: Maximum number of results to return
            case_sensitive: Whether search should be case-sensitive

        Returns:
            List of SearchResult objects sorted by relevance
        """
        if search_dir is None:
            search_dir = self.search_dir

        if not search_dir.exists():
            raise ValueError(f"Search directory does not exist: {search_dir}")

        if not query or not query.strip():
            return []

        jsonl_files = self.adapter.metadata.find_sessions(
            search_dir, include_subagents=True
        )
        if not jsonl_files:
            return []

        if date_from or date_to:
            jsonl_files = self._filter_files_by_date(jsonl_files, date_from, date_to)

        # Select matching strategy
        matcher = self._get_matcher(mode, query, case_sensitive)
        if matcher is None:
            return []  # e.g. invalid regex

        # Search all files
        all_results = []
        for jsonl_file in jsonl_files:
            results = self._search_file(jsonl_file, matcher, speaker_filter)
            all_results.extend(results)

        all_results.sort(key=lambda x: x.relevance_score, reverse=True)
        return all_results[:max_results]

    def search_by_date_range(
        self, date_from: datetime, date_to: datetime, search_dir: Optional[Path] = None
    ) -> List[Path]:
        """Find all conversation files within a date range."""
        if search_dir is None:
            search_dir = self.search_dir

        jsonl_files = self.adapter.metadata.find_sessions(
            search_dir, include_subagents=True
        )
        return self._filter_files_by_date(jsonl_files, date_from, date_to)

    def get_conversation_topics(
        self, jsonl_file: Path, max_topics: int = 5
    ) -> List[str]:
        """Extract main topics from a conversation using NLP."""
        if not self.nlp:
            return []

        all_content = []
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        content = self._extract_content(entry)
                        if content:
                            all_content.append(content)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        if not all_content:
            return []

        full_text = " ".join(all_content[:10])
        doc = self.nlp(full_text)

        noun_phrases = []
        for chunk in doc.noun_chunks:
            if len(chunk.text.split()) <= 3:
                noun_phrases.append(chunk.text.lower())

        phrase_counts: Dict[str, int] = {}
        for phrase in noun_phrases:
            phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1

        sorted_phrases = sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True)
        return [phrase for phrase, count in sorted_phrases[:max_topics] if count > 1]

    # ── Core search engine ───────────────────────────────────────────

    def _get_matcher(self, mode: str, query: str, case_sensitive: bool):
        """Return a match function for the given mode.

        A matcher takes (content: str) and returns (relevance, matched_content, context)
        or None if no match.
        """
        if mode == "regex":
            return self._make_regex_matcher(query, case_sensitive)
        elif mode == "exact":
            return self._make_exact_matcher(query, case_sensitive)
        elif mode == "semantic" and self.nlp:
            return self._make_semantic_matcher(query)
        else:
            return self._make_smart_matcher(query, case_sensitive)

    def _search_file(self, jsonl_file, matcher, speaker_filter):
        """Search a single JSONL file using the provided matcher function.

        This is the common iteration logic shared by all search modes.
        """
        results = []
        conversation_id = jsonl_file.stem

        for content, speaker, timestamp, line_num in self._iter_messages(
            jsonl_file, speaker_filter
        ):
            match = matcher(content)
            if match is not None:
                relevance, matched_content, context = match
                results.append(
                    SearchResult(
                        file_path=jsonl_file,
                        conversation_id=conversation_id,
                        matched_content=matched_content,
                        context=context,
                        speaker=speaker,
                        timestamp=timestamp,
                        relevance_score=relevance,
                        line_number=line_num,
                    )
                )

        return results

    def _iter_messages(self, jsonl_file, speaker_filter=None):
        """Yield (content, speaker, timestamp, line_num) for each message.

        Handles file reading, JSON parsing, speaker filtering, and
        timestamp parsing — the boilerplate shared by all search modes.
        Per-entry content/speaker extraction is delegated to the adapter.
        """
        extract = self.adapter.parsers.extract_search_content
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        entry = json.loads(line.strip())
                        result = extract(entry)
                        if result is None:
                            continue
                        content, speaker = result
                        if not content:
                            continue
                        if speaker_filter and speaker != speaker_filter:
                            continue

                        timestamp = self._parse_timestamp(entry.get("timestamp"))
                        yield content, speaker, timestamp, line_num

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error searching {jsonl_file}: {e}")

    # ── Matcher factories ────────────────────────────────────────────

    def _make_smart_matcher(self, query, case_sensitive):
        """Create a smart matcher combining exact and token-based matching."""
        if not case_sensitive:
            query_tokens = set(query.lower().split()) - self.stop_words
        else:
            query_tokens = set(query.split()) - self.stop_words

        def match(content):
            relevance = self._calculate_relevance(content, query, query_tokens, case_sensitive)
            if relevance > 0.1:
                context = self._extract_context(content, query, case_sensitive)
                return relevance, content[:200], context
            return None

        return match

    def _make_exact_matcher(self, query, case_sensitive):
        """Create an exact string matching matcher."""
        search_query = query if case_sensitive else query.lower()

        def match(content):
            search_content = content if case_sensitive else content.lower()
            if search_query in search_content:
                match_count = search_content.count(search_query)
                relevance = min(1.0, match_count * 0.2)
                context = self._extract_context(content, query, case_sensitive)
                return relevance, content[:200], context
            return None

        return match

    def _make_regex_matcher(self, pattern, case_sensitive):
        """Create a regex pattern matcher. Returns None if pattern is invalid."""
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            print(f"Invalid regex pattern: {e}")
            return None

        def match(content):
            matches = list(regex.finditer(content))
            if matches:
                relevance = min(1.0, len(matches) * 0.2)
                first_match = matches[0]
                start = max(0, first_match.start() - 100)
                end = min(len(content), first_match.end() + 100)
                context = "..." + content[start:end] + "..."
                return relevance, first_match.group(), context
            return None

        return match

    def _make_semantic_matcher(self, query):
        """Create a semantic similarity matcher using spaCy."""
        if not self.nlp:
            return lambda content: None

        query_doc = self.nlp(query.lower())
        query_tokens = [
            token for token in query_doc if not token.is_stop and token.is_alpha
        ]

        def match(content):
            content_doc = self.nlp(content.lower())
            similarity = self._calculate_semantic_similarity(
                query_doc, query_tokens, content_doc
            )
            if similarity > 0.3:
                context = self._extract_context(content, query, False)
                return similarity, content[:200], context
            return None

        return match

    # ── Content extraction ───────────────────────────────────────────

    def _extract_content(self, entry: Dict) -> str:
        """Extract text content from a JSONL entry via the adapter.

        Returns empty string for entries the adapter doesn't recognize
        (tool calls, system messages, envelope metadata, etc.).
        """
        result = self.adapter.parsers.extract_search_content(entry)
        return result[0] if result else ""

    # ── Relevance scoring ────────────────────────────────────────────

    def _calculate_relevance(
        self, content: str, query: str, query_tokens: Set[str], case_sensitive: bool
    ) -> float:
        """Calculate relevance score using exact match, token overlap, and proximity."""
        relevance = 0.0

        if not case_sensitive:
            content_lower = content.lower()
            query_lower = query.lower()
        else:
            content_lower = content
            query_lower = query

        # Exact match bonus
        if query_lower in content_lower:
            relevance += 0.5
            count = content_lower.count(query_lower)
            relevance += min(0.3, count * 0.1)

        # Token overlap
        content_tokens = set(content_lower.split()) - self.stop_words
        if query_tokens and content_tokens:
            overlap = len(query_tokens & content_tokens)
            relevance += min(0.4, overlap / len(query_tokens) * 0.4)

        # Proximity bonus — are query terms near each other?
        if len(query_tokens) > 1:
            words = content_lower.split()
            for i in range(len(words) - len(query_tokens)):
                window = set(words[i: i + len(query_tokens) * 2])
                if query_tokens.issubset(window):
                    relevance += 0.1
                    break

        return min(1.0, relevance)

    def _calculate_semantic_similarity(
        self, query_doc, query_tokens, content_doc
    ) -> float:
        """Calculate semantic similarity using spaCy."""
        if not query_tokens:
            return 0.0

        similar_count = 0
        for query_token in query_tokens:
            for content_token in content_doc:
                if content_token.is_alpha and not content_token.is_stop:
                    if (
                        query_token.lemma_ == content_token.lemma_
                        or query_token.text == content_token.text
                    ):
                        similar_count += 1
                        break

        if query_tokens:
            base_similarity = similar_count / len(query_tokens)
        else:
            base_similarity = 0.0

        if query_doc.text.lower() in content_doc.text.lower():
            base_similarity = min(1.0, base_similarity + 0.3)

        return base_similarity

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse an ISO timestamp string, returning None on failure."""
        if not timestamp_str:
            return None
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _extract_context(
        self, content: str, query: str, case_sensitive: bool, context_size: int = 150
    ) -> str:
        """Extract context around the match for display."""
        if not case_sensitive:
            pos = content.lower().find(query.lower())
        else:
            pos = content.find(query)

        if pos == -1:
            return content[: context_size * 2] + (
                "..." if len(content) > context_size * 2 else ""
            )

        start = max(0, pos - context_size)
        end = min(len(content), pos + len(query) + context_size)

        context = content[start:end]

        if start > 0:
            context = "..." + context
        if end < len(content):
            context = context + "..."

        # Highlight the match
        if not case_sensitive:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            context = pattern.sub(f"**{query.upper()}**", context)
        else:
            context = context.replace(query, f"**{query}**")

        return context

    @staticmethod
    def _filter_files_by_date(
        files: List[Path],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[Path]:
        """Filter files by modification date."""
        filtered = []
        for file in files:
            file_mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if date_from and file_mtime < date_from:
                continue
            if date_to and file_mtime > date_to:
                continue
            filtered.append(file)
        return filtered


def create_search_index(search_dir: Path, output_file: Path) -> None:
    """
    Create a search index for faster subsequent searches.

    This pre-processes all conversations and saves metadata.
    """
    index = {"created": datetime.now().isoformat(), "conversations": {}}

    jsonl_files = list(search_dir.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        conv_id = jsonl_file.stem

        file_metadata = {
            "path": str(jsonl_file),
            "modified": datetime.fromtimestamp(jsonl_file.stat().st_mtime).isoformat(),
            "size": jsonl_file.stat().st_size,
            "message_count": 0,
            "speakers": set(),
            "first_message": None,
            "last_message": None,
        }

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("type") in ["user", "assistant"]:
                            file_metadata["message_count"] += 1
                            speaker = (
                                "human" if entry["type"] == "user" else "assistant"
                            )
                            file_metadata["speakers"].add(speaker)

                            if file_metadata["first_message"] is None:
                                file_metadata["first_message"] = entry.get("timestamp")
                            file_metadata["last_message"] = entry.get("timestamp")

                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

        file_metadata["speakers"] = list(file_metadata["speakers"])
        index["conversations"][conv_id] = file_metadata

    with open(output_file, "w") as f:
        json.dump(index, f, indent=2)

    print(f"Created search index with {len(index['conversations'])} conversations")


# Example usage and testing
if __name__ == "__main__":
    from datetime import timedelta

    searcher = ConversationSearcher()

    print("Testing search functionality...")

    results = searcher.search("python error", mode="smart", max_results=5)
    print(f"\nFound {len(results)} results for 'python error'")
    for result in results[:2]:
        print(result)

    results = searcher.search(r"import\s+\w+", mode="regex", max_results=5)
    print(f"\nFound {len(results)} results for regex 'import\\s+\\w+'")

    week_ago = datetime.now() - timedelta(days=7)
    results = searcher.search("", date_from=week_ago, max_results=5)
    print(f"\nFound {len(results)} conversations from the last week")
