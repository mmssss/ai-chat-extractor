#!/usr/bin/env python3
"""
Extract clean conversation logs from Claude Code's internal JSONL files

This tool parses the undocumented JSONL format used by Claude Code to store
conversations locally in ~/.claude/projects/ and exports them as clean,
readable markdown files.
"""

import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ClaudeConversationExtractor:
    """Extract and convert Claude Code conversations from JSONL to markdown."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize the extractor with Claude's directory and output location."""
        self.claude_dir = Path.home() / ".claude" / "projects"

        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Try multiple possible output directories
            possible_dirs = [
                Path.home() / "Desktop" / "Claude logs",
                Path.home() / "Documents" / "Claude logs",
                Path.home() / "Claude logs",
                Path.cwd() / "claude-logs",
            ]

            # Use the first directory we can create
            for dir_path in possible_dirs:
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    # Test if we can write to it
                    test_file = dir_path / ".test"
                    test_file.touch()
                    test_file.unlink()
                    self.output_dir = dir_path
                    break
                except Exception:
                    continue
            else:
                # Fallback to current directory
                self.output_dir = Path.cwd() / "claude-logs"
                self.output_dir.mkdir(exist_ok=True)

        print(f"📁 Saving logs to: {self.output_dir}")

    def find_sessions(self, project_path: Optional[str] = None, include_subagents: bool = False) -> List[Path]:
        """Find all JSONL session files, sorted by most recent first.
        
        Args:
            project_path: Optional project subdirectory to search in
            include_subagents: If True, include subagent JSONL files in results.
                              If False (default), only return main conversation files.
        """
        if project_path:
            search_dir = self.claude_dir / project_path
        else:
            search_dir = self.claude_dir

        sessions = []
        if search_dir.exists():
            for jsonl_file in search_dir.rglob("*.jsonl"):
                if not include_subagents and "/subagents/" in str(jsonl_file):
                    continue
                sessions.append(jsonl_file)
        return sorted(sessions, key=lambda x: x.stat().st_mtime, reverse=True)

    def find_subagents(self, session_path: Path) -> List[Path]:
        """Find all subagent JSONL files associated with a main conversation.
        
        Args:
            session_path: Path to the main conversation JSONL file
            
        Returns:
            List of paths to subagent JSONL files, sorted by modification time
        """
        session_id = session_path.stem
        session_dir = session_path.parent / session_id
        subagents_dir = session_dir / "subagents"
        
        if not subagents_dir.exists():
            return []
        
        subagent_files = sorted(
            [f for f in subagents_dir.glob("agent-*.jsonl")],
            key=lambda x: x.stat().st_mtime
        )
        return subagent_files

    def get_subagent_metadata(self, subagent_path: Path) -> Dict:
        """Get metadata for a subagent from its .meta.json file and JSONL content.
        
        Args:
            subagent_path: Path to the subagent JSONL file
            
        Returns:
            Dict with agent metadata: agentId, agentType, first_message, entry_count, etc.
        """
        meta = {
            "agentId": "",
            "agentType": "unknown",
            "first_message": "",
            "entry_count": 0,
            "first_timestamp": "",
            "last_timestamp": "",
        }
        
        # Extract agentId from filename: agent-<agentId>.jsonl
        filename = subagent_path.stem  # agent-<agentId>
        if filename.startswith("agent-"):
            meta["agentId"] = filename[6:]
        
        # Read .meta.json if it exists
        meta_json_path = subagent_path.with_suffix(".meta.json")
        if meta_json_path.exists():
            try:
                with open(meta_json_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                    meta["agentType"] = meta_data.get("agentType", "unknown")
            except Exception:
                pass
        
        # Read first user message and timestamps from JSONL
        try:
            with open(subagent_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        meta["entry_count"] += 1
                        
                        ts = entry.get("timestamp", "")
                        if ts and not meta["first_timestamp"]:
                            meta["first_timestamp"] = ts
                        if ts:
                            meta["last_timestamp"] = ts
                        
                        # Get first user message as description
                        if not meta["first_message"] and entry.get("type") == "user":
                            msg = entry.get("message", {})
                            if isinstance(msg, dict):
                                content = msg.get("content", "")
                                text = self._extract_text_content(content)
                                if text:
                                    meta["first_message"] = text[:200]
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        
        return meta

    @staticmethod
    def _is_ide_preamble(text: str) -> bool:
        """Check if text is an IDE-generated preamble rather than real user input."""
        preamble_patterns = [
            "The user opened the file",
            "The user selected the lines",
            "The user is currently viewing",
            "The user has the following",
            "Caveat: The messages below",
        ]
        return any(text.startswith(p) for p in preamble_patterns)

    @staticmethod
    def _clean_slash_command(text: str) -> str:
        """Clean up slash command text that gets duplicated by IDE.
        
        The IDE sometimes produces: '/command             command             args'
        This cleans it to: '/command args'
        
        Also handles non-slash duplicates: 'extra-usage             extra-usage'
        """
        # Slash command with duplicate: /word<whitespace>word<whitespace>rest
        match = re.match(r'^/(\S+)\s+\1(?:\s+(.*))?$', text, re.DOTALL)
        if match:
            rest = (match.group(2) or "").strip()
            return f"/{match.group(1)} {rest}".strip() if rest else f"/{match.group(1)}"
        # Non-slash duplicate: word<whitespace>word
        match = re.match(r'^(\S+)\s+\1(?:\s+(.*))?$', text, re.DOTALL)
        if match:
            rest = (match.group(2) or "").strip()
            return f"{match.group(1)} {rest}".strip() if rest else match.group(1)
        return text

    @staticmethod
    def _extract_first_user_text(jsonl_path: Path) -> str:
        """Extract the first meaningful user message text from a JSONL file.
        
        Skips meta messages, IDE preambles, tool results, interruptions,
        and system continuations. Returns empty string if no meaningful
        message found.
        """
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data.get("type") != "user" or "message" not in data:
                            continue
                        # Skip meta entries (local commands, etc.)
                        if data.get("isMeta"):
                            continue
                        msg = data["message"]
                        if not isinstance(msg, dict) or msg.get("role") != "user":
                            continue
                        content = msg.get("content", "")
                        
                        if isinstance(content, list):
                            for item in content:
                                if not isinstance(item, dict) or item.get("type") != "text":
                                    continue
                                text = item.get("text", "").strip()
                                # Skip tool results
                                if text.startswith("tool_use_id"):
                                    continue
                                # Skip interruptions
                                if "[Request interrupted" in text:
                                    continue
                                # Skip session continuations
                                if "session is being continued" in text.lower():
                                    continue
                                # Remove XML-like tags and ANSI escape codes
                                text = re.sub(r'<[^>]+>', '', text).strip()
                                text = re.sub(r'\x1b\[[0-9;]*m', '', text).strip()
                                # Skip command outputs
                                if "is running" in text and "…" in text:
                                    continue
                                # Skip IDE-generated preambles
                                if ClaudeConversationExtractor._is_ide_preamble(text):
                                    continue
                                # Clean up slash command duplication
                                text = ClaudeConversationExtractor._clean_slash_command(text)
                                # Skip bare slash commands (e.g. /help, /config, /sandbox)
                                if re.match(r'^/\w+$', text):
                                    continue
                                if text and len(text) > 3:
                                    return text[:100].replace('\n', ' ').strip()
                        elif isinstance(content, str):
                            text = content.strip()
                            text = re.sub(r'<[^>]+>', '', text).strip()
                            text = re.sub(r'\x1b\[[0-9;]*m', '', text).strip()
                            if "is running" in text and "…" in text:
                                continue
                            if "session is being continued" in text.lower():
                                continue
                            if ClaudeConversationExtractor._is_ide_preamble(text):
                                continue
                            text = ClaudeConversationExtractor._clean_slash_command(text)
                            # Skip bare slash commands
                            if re.match(r'^/\w+$', text):
                                continue
                            if not text.startswith("tool_use_id") and "[Request interrupted" not in text:
                                if text and len(text) > 3:
                                    return text[:100].replace('\n', ' ').strip()
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return ""

    @staticmethod
    def extract_session_metadata(jsonl_path: Path) -> Dict:
        """Extract all available metadata from a conversation JSONL file.
        
        Returns dict with: slug, custom_title, first_user_message, sessionId,
        first_timestamp, last_timestamp, models, version, gitBranch, cwd,
        project_path, entry_count, has_subagents, subagent_count
        """
        metadata = {
            "slug": "",
            "custom_title": "",
            "first_user_message": "",
            "sessionId": "",
            "first_timestamp": "",
            "last_timestamp": "",
            "models": set(),
            "version": "",
            "gitBranch": "",
            "cwd": "",
            "project_path": "",
            "entry_count": 0,
            "has_subagents": False,
            "subagent_count": 0,
            "has_errors": False,
        }
        
        # Derive project from directory name
        metadata["project_path"] = jsonl_path.parent.name
        metadata["sessionId"] = jsonl_path.stem
        
        # Check for subagents directory
        session_dir = jsonl_path.parent / jsonl_path.stem
        subagents_dir = session_dir / "subagents"
        if subagents_dir.exists():
            sa_files = list(subagents_dir.glob("agent-*.jsonl"))
            metadata["has_subagents"] = len(sa_files) > 0
            metadata["subagent_count"] = len(sa_files)
        
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        metadata["entry_count"] += 1
                        
                        # Custom title (user-set via /rename command)
                        # The last one wins (user may rename multiple times)
                        if entry.get("type") == "custom-title":
                            title = entry.get("title", "") or entry.get("customTitle", "")
                            if title:
                                metadata["custom_title"] = title
                        
                        # Slug (random internal name)
                        if not metadata["slug"] and entry.get("slug"):
                            metadata["slug"] = entry["slug"]
                        
                        # Timestamps
                        ts = entry.get("timestamp", "")
                        if ts and not metadata["first_timestamp"]:
                            metadata["first_timestamp"] = ts
                        if ts:
                            metadata["last_timestamp"] = ts
                        
                        # Version
                        if not metadata["version"] and entry.get("version"):
                            metadata["version"] = entry["version"]
                        
                        # Git branch
                        if not metadata["gitBranch"] and entry.get("gitBranch"):
                            metadata["gitBranch"] = entry["gitBranch"]
                        
                        # Working directory
                        if not metadata["cwd"] and entry.get("cwd"):
                            metadata["cwd"] = entry["cwd"]
                        
                        # Models used
                        if entry.get("type") == "assistant" and isinstance(entry.get("message"), dict):
                            model = entry["message"].get("model", "")
                            if model and model != "<synthetic>":
                                metadata["models"].add(model)
                        
                        # Errors
                        if entry.get("error") or entry.get("isApiErrorMessage"):
                            metadata["has_errors"] = True
                        
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        
        # Convert set to sorted list for serialization
        metadata["models"] = sorted(metadata["models"])
        
        # Extract first user message (separate pass for clarity)
        metadata["first_user_message"] = ClaudeConversationExtractor._extract_first_user_text(jsonl_path)
        
        return metadata

    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to a URL/filename-safe slug.
        
        Examples:
            'glistening-foraging-snail' -> 'glistening-foraging-snail'
            'My Cool Conversation!' -> 'my-cool-conversation'
            'Fix bug in auth/login.py' -> 'fix-bug-in-auth-login-py'
        """
        # Normalize unicode characters
        text = unicodedata.normalize("NFKD", text)
        # Convert to lowercase
        text = text.lower()
        # Replace any non-alphanumeric chars (except hyphens) with hyphens
        text = re.sub(r"[^a-z0-9\-]", "-", text)
        # Collapse multiple hyphens
        text = re.sub(r"-+", "-", text)
        # Strip leading/trailing hyphens
        text = text.strip("-")
        # Truncate to reasonable length for filenames
        if len(text) > 60:
            text = text[:60].rstrip("-")
        return text

    def _slug_from_metadata(self, metadata: Dict) -> str:
        """Derive a filename slug from metadata, with priority chain:
        
        1. custom_title (user-set via /rename)
        2. first_user_message (content-based)
        3. session ID prefix (fallback)
        """
        if metadata.get("custom_title"):
            return self.slugify(metadata["custom_title"])
        if metadata.get("first_user_message"):
            return self.slugify(metadata["first_user_message"])
        return metadata.get("sessionId", "unknown")[:8]

    def _resolve_output_path(self, filename: str) -> Optional[Path]:
        """Resolve output path, skipping if file already exists.
        
        Returns:
            Path to write to, or None if the file already exists (skip).
        """
        path = self.output_dir / filename
        if path.exists():
            return None
        return path

    def generate_filename(self, session_path: Path, format: str = "markdown") -> str:
        """Generate output filename from conversation metadata.
        
        Format: 20260311T081823_claude_<slug>.<ext>
        
        Priority for slug:
        1. custom_title — user-set name via /rename command
        2. first_user_message — slugified first meaningful user message
        3. session ID prefix — first 8 chars of the UUID
        
        Args:
            session_path: Path to the JSONL file
            format: Output format ('markdown', 'json', 'html')
            
        Returns:
            Generated filename string
        """
        ext_map = {"markdown": "md", "json": "json", "html": "html"}
        ext = ext_map.get(format, "md")
        
        metadata = self.extract_session_metadata(session_path)
        
        # Build timestamp part
        first_ts = metadata["first_timestamp"]
        if first_ts:
            try:
                dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                ts_part = dt.strftime("%Y%m%dT%H%M%S")
            except Exception:
                ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")
        else:
            ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")
        
        # Build slug part with priority chain
        slug_part = self._slug_from_metadata(metadata)
        
        return f"{ts_part}_claude_{slug_part}.{ext}"

    def generate_subagent_filename(
        self, subagent_path: Path, parent_metadata: Dict, agent_index: int, format: str = "markdown"
    ) -> str:
        """Generate output filename for a subagent conversation.
        
        Format: 20260311T081823_claude_<parent-slug>_agent<N>_<agentId-short>.<ext>
        
        The parent slug uses the same priority chain as generate_filename:
        custom_title → first_user_message → session ID prefix
        
        Args:
            subagent_path: Path to the subagent JSONL file
            parent_metadata: Metadata dict from the parent conversation
            agent_index: 1-based index of this agent among siblings
            format: Output format
            
        Returns:
            Generated filename string
        """
        ext_map = {"markdown": "md", "json": "json", "html": "html"}
        ext = ext_map.get(format, "md")
        
        # Use parent's timestamp
        first_ts = parent_metadata.get("first_timestamp", "")
        if first_ts:
            try:
                dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                ts_part = dt.strftime("%Y%m%dT%H%M%S")
            except Exception:
                ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")
        else:
            ts_part = datetime.now().strftime("%Y%m%dT%H%M%S")
        
        # Parent slug with priority chain
        parent_slug = self._slug_from_metadata(parent_metadata)
        
        # Agent ID (short)
        agent_meta = self.get_subagent_metadata(subagent_path)
        agent_id_short = agent_meta["agentId"][:8] if agent_meta["agentId"] else "unknown"
        
        return f"{ts_part}_claude_{parent_slug}_agent{agent_index}_{agent_id_short}.{ext}"

    def extract_conversation(self, jsonl_path: Path, detailed: bool = False) -> List[Dict[str, str]]:
        """Extract conversation messages from a JSONL file.
        
        Args:
            jsonl_path: Path to the JSONL file
            detailed: If True, include tool use, MCP responses, and system messages
        """
        conversation = []

        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Extract user messages
                        if entry.get("type") == "user" and "message" in entry:
                            msg = entry["message"]
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                content = msg.get("content", "")
                                text = self._extract_text_content(content)

                                if text and text.strip():
                                    conversation.append(
                                        {
                                            "role": "user",
                                            "content": text,
                                            "timestamp": entry.get("timestamp", ""),
                                        }
                                    )

                        # Extract assistant messages
                        elif entry.get("type") == "assistant" and "message" in entry:
                            msg = entry["message"]
                            if isinstance(msg, dict) and msg.get("role") == "assistant":
                                content = msg.get("content", [])
                                text = self._extract_text_content(content, detailed=detailed)

                                if text and text.strip():
                                    conversation.append(
                                        {
                                            "role": "assistant",
                                            "content": text,
                                            "timestamp": entry.get("timestamp", ""),
                                        }
                                    )
                        
                        # Include tool use and system messages if detailed mode
                        elif detailed:
                            # Extract tool use events
                            if entry.get("type") == "tool_use":
                                tool_data = entry.get("tool", {})
                                tool_name = tool_data.get("name", "unknown")
                                tool_input = tool_data.get("input", {})
                                conversation.append(
                                    {
                                        "role": "tool_use",
                                        "content": f"🔧 Tool: {tool_name}\nInput: {json.dumps(tool_input, indent=2)}",
                                        "timestamp": entry.get("timestamp", ""),
                                    }
                                )
                            
                            # Extract tool results
                            elif entry.get("type") == "tool_result":
                                result = entry.get("result", {})
                                output = result.get("output", "") or result.get("error", "")
                                conversation.append(
                                    {
                                        "role": "tool_result",
                                        "content": f"📤 Result:\n{output}",
                                        "timestamp": entry.get("timestamp", ""),
                                    }
                                )
                            
                            # Extract system messages
                            elif entry.get("type") == "system" and "message" in entry:
                                msg = entry.get("message", "")
                                if msg:
                                    conversation.append(
                                        {
                                            "role": "system",
                                            "content": f"ℹ️ System: {msg}",
                                            "timestamp": entry.get("timestamp", ""),
                                        }
                                    )

                    except json.JSONDecodeError:
                        continue
                    except Exception:
                        # Silently skip problematic entries
                        continue

        except Exception as e:
            print(f"❌ Error reading file {jsonl_path}: {e}")

        return conversation

    def _extract_text_content(self, content, detailed: bool = False) -> str:
        """Extract text from various content formats Claude uses.
        
        Args:
            content: The content to extract from
            detailed: If True, include tool use blocks and other metadata
        """
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Extract text from content array
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif detailed and item.get("type") == "tool_use":
                        # Include tool use details in detailed mode
                        tool_name = item.get("name", "unknown")
                        tool_input = item.get("input", {})
                        text_parts.append(f"\n🔧 Using tool: {tool_name}")
                        text_parts.append(f"Input: {json.dumps(tool_input, indent=2)}\n")
            return "\n".join(text_parts)
        else:
            return str(content)

    def display_conversation(self, jsonl_path: Path, detailed: bool = False) -> None:
        """Display a conversation in the terminal with pagination.
        
        Args:
            jsonl_path: Path to the JSONL file
            detailed: If True, include tool use and system messages
        """
        try:
            # Extract conversation
            messages = self.extract_conversation(jsonl_path, detailed=detailed)
            
            if not messages:
                print("❌ No messages found in conversation")
                return
            
            # Get session info
            session_id = jsonl_path.stem
            
            # Clear screen and show header
            print("\033[2J\033[H", end="")  # Clear screen
            print("=" * 60)
            print(f"📄 Viewing: {jsonl_path.parent.name}")
            print(f"Session: {session_id[:8]}...")
            
            # Get timestamp from first message
            first_timestamp = messages[0].get("timestamp", "")
            if first_timestamp:
                try:
                    dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
                    print(f"Date: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except Exception:
                    pass
            
            print("=" * 60)
            print("↑↓ to scroll • Q to quit • Enter to continue\n")
            
            # Display messages with pagination
            lines_shown = 8  # Header lines
            lines_per_page = 30
            
            for i, msg in enumerate(messages):
                role = msg["role"]
                content = msg["content"]
                
                # Format role display
                if role == "user" or role == "human":
                    print(f"\n{'─' * 40}")
                    print(f"👤 HUMAN:")
                    print(f"{'─' * 40}")
                elif role == "assistant":
                    print(f"\n{'─' * 40}")
                    print(f"🤖 CLAUDE:")
                    print(f"{'─' * 40}")
                elif role == "tool_use":
                    print(f"\n🔧 TOOL USE:")
                elif role == "tool_result":
                    print(f"\n📤 TOOL RESULT:")
                elif role == "system":
                    print(f"\nℹ️ SYSTEM:")
                else:
                    print(f"\n{role.upper()}:")
                
                # Display content (limit very long messages)
                lines = content.split('\n')
                max_lines_per_msg = 50
                
                for line_idx, line in enumerate(lines[:max_lines_per_msg]):
                    # Wrap very long lines
                    if len(line) > 100:
                        line = line[:97] + "..."
                    print(line)
                    lines_shown += 1
                    
                    # Check if we need to paginate
                    if lines_shown >= lines_per_page:
                        response = input("\n[Enter] Continue • [Q] Quit: ").strip().upper()
                        if response == "Q":
                            print("\n👋 Stopped viewing")
                            return
                        # Clear screen for next page
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

    def save_as_markdown(
        self, conversation: List[Dict[str, str]], session_id: str,
        session_path: Optional[Path] = None, filename_override: Optional[str] = None
    ) -> Optional[Path]:
        """Save conversation as clean markdown file.
        
        Args:
            conversation: List of message dicts
            session_id: Session identifier (UUID)
            session_path: Optional path to JSONL file for metadata-based filename
            filename_override: Optional explicit filename to use
        """
        if not conversation:
            return None

        # Get timestamp from first message
        first_timestamp = conversation[0].get("timestamp", "")
        if first_timestamp:
            try:
                # Parse ISO timestamp
                dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                date_str = datetime.now().strftime("%Y-%m-%d")
                time_str = ""
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = ""

        if filename_override:
            filename = filename_override
        elif session_path:
            filename = self.generate_filename(session_path, format="markdown")
        else:
            filename = f"claude-conversation-{date_str}-{session_id[:8]}.md"
        output_path = self._resolve_output_path(filename)
        if output_path is None:
            return None

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Claude Conversation Log\n\n")
            f.write(f"Session ID: {session_id}\n")
            f.write(f"Date: {date_str}")
            if time_str:
                f.write(f" {time_str}")
            f.write("\n\n---\n\n")

            for msg in conversation:
                role = msg["role"]
                content = msg["content"]
                
                if role == "user":
                    f.write("## 👤 User\n\n")
                    f.write(f"{content}\n\n")
                elif role == "assistant":
                    f.write("## 🤖 Claude\n\n")
                    f.write(f"{content}\n\n")
                elif role == "tool_use":
                    f.write("### 🔧 Tool Use\n\n")
                    f.write(f"{content}\n\n")
                elif role == "tool_result":
                    f.write("### 📤 Tool Result\n\n")
                    f.write(f"{content}\n\n")
                elif role == "system":
                    f.write("### ℹ️ System\n\n")
                    f.write(f"{content}\n\n")
                else:
                    f.write(f"## {role}\n\n")
                    f.write(f"{content}\n\n")
                f.write("---\n\n")

        return output_path
    
    def save_as_json(
        self, conversation: List[Dict[str, str]], session_id: str,
        session_path: Optional[Path] = None, filename_override: Optional[str] = None
    ) -> Optional[Path]:
        """Save conversation as JSON file.
        
        Args:
            conversation: List of message dicts
            session_id: Session identifier (UUID)
            session_path: Optional path to JSONL file for metadata-based filename
            filename_override: Optional explicit filename to use
        """
        if not conversation:
            return None

        # Get timestamp from first message
        first_timestamp = conversation[0].get("timestamp", "")
        if first_timestamp:
            try:
                dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.now().strftime("%Y-%m-%d")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

        if filename_override:
            filename = filename_override
        elif session_path:
            filename = self.generate_filename(session_path, format="json")
        else:
            filename = f"claude-conversation-{date_str}-{session_id[:8]}.json"
        output_path = self._resolve_output_path(filename)
        if output_path is None:
            return None

        # Create JSON structure
        output = {
            "session_id": session_id,
            "date": date_str,
            "message_count": len(conversation),
            "messages": conversation
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        return output_path
    
    def save_as_html(
        self, conversation: List[Dict[str, str]], session_id: str,
        session_path: Optional[Path] = None, filename_override: Optional[str] = None
    ) -> Optional[Path]:
        """Save conversation as HTML file with syntax highlighting.
        
        Args:
            conversation: List of message dicts
            session_id: Session identifier (UUID)
            session_path: Optional path to JSONL file for metadata-based filename
            filename_override: Optional explicit filename to use
        """
        if not conversation:
            return None

        # Get timestamp from first message
        first_timestamp = conversation[0].get("timestamp", "")
        if first_timestamp:
            try:
                dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                date_str = datetime.now().strftime("%Y-%m-%d")
                time_str = ""
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = ""

        if filename_override:
            filename = filename_override
        elif session_path:
            filename = self.generate_filename(session_path, format="html")
        else:
            filename = f"claude-conversation-{date_str}-{session_id[:8]}.html"
        output_path = self._resolve_output_path(filename)
        if output_path is None:
            return None

        # HTML template with modern styling
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Conversation - {session_id[:8]}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            margin: 0 0 10px 0;
        }}
        .metadata {{
            color: #666;
            font-size: 0.9em;
        }}
        .message {{
            background: white;
            padding: 15px 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .user {{
            border-left: 4px solid #3498db;
        }}
        .assistant {{
            border-left: 4px solid #2ecc71;
        }}
        .tool_use {{
            border-left: 4px solid #f39c12;
            background: #fffbf0;
        }}
        .tool_result {{
            border-left: 4px solid #e74c3c;
            background: #fff5f5;
        }}
        .system {{
            border-left: 4px solid #95a5a6;
            background: #f8f9fa;
        }}
        .role {{
            font-weight: bold;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
        }}
        .content {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        pre {{
            background: #f4f4f4;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Claude Conversation Log</h1>
        <div class="metadata">
            <p>Session ID: {session_id}</p>
            <p>Date: {date_str} {time_str}</p>
            <p>Messages: {len(conversation)}</p>
        </div>
    </div>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
            for msg in conversation:
                role = msg["role"]
                content = msg["content"]
                
                # Escape HTML
                content = content.replace("&", "&amp;")
                content = content.replace("<", "&lt;")
                content = content.replace(">", "&gt;")
                
                role_display = {
                    "user": "👤 User",
                    "assistant": "🤖 Claude",
                    "tool_use": "🔧 Tool Use",
                    "tool_result": "📤 Tool Result",
                    "system": "ℹ️ System"
                }.get(role, role)
                
                f.write(f'    <div class="message {role}">\n')
                f.write(f'        <div class="role">{role_display}</div>\n')
                f.write(f'        <div class="content">{content}</div>\n')
                f.write(f'    </div>\n')
            
            f.write("\n</body>\n</html>")

        return output_path

    def save_conversation(
        self, conversation: List[Dict[str, str]], session_id: str, format: str = "markdown",
        session_path: Optional[Path] = None, filename_override: Optional[str] = None
    ) -> Optional[Path]:
        """Save conversation in the specified format.
        
        Args:
            conversation: The conversation data
            session_id: Session identifier
            format: Output format ('markdown', 'json', 'html')
            session_path: Optional path to JSONL file for metadata-based filename
            filename_override: Optional explicit filename to use
        """
        kwargs = {"session_path": session_path, "filename_override": filename_override}
        if format == "markdown":
            return self.save_as_markdown(conversation, session_id, **kwargs)
        elif format == "json":
            return self.save_as_json(conversation, session_id, **kwargs)
        elif format == "html":
            return self.save_as_html(conversation, session_id, **kwargs)
        else:
            print(f"❌ Unsupported format: {format}")
            return None

    def get_conversation_preview(self, session_path: Path) -> Tuple[str, int]:
        """Get a preview of the conversation's first real user message and message count."""
        try:
            first_user_msg = ""
            msg_count = 0
            
            with open(session_path, 'r', encoding='utf-8') as f:
                for line in f:
                    msg_count += 1
                    if not first_user_msg:
                        try:
                            data = json.loads(line)
                            # Check for user message
                            if data.get("type") == "user" and "message" in data:
                                msg = data["message"]
                                if msg.get("role") == "user":
                                    content = msg.get("content", "")
                                    
                                    # Handle list content (common format in Claude JSONL)
                                    if isinstance(content, list):
                                        for item in content:
                                            if isinstance(item, dict) and item.get("type") == "text":
                                                text = item.get("text", "").strip()
                                                
                                                # Skip tool results
                                                if text.startswith("tool_use_id"):
                                                    continue
                                                
                                                # Skip interruption messages
                                                if "[Request interrupted" in text:
                                                    continue
                                                
                                                # Skip Claude's session continuation messages
                                                if "session is being continued" in text.lower():
                                                    continue
                                                
                                                # Remove XML-like tags (command messages, etc)
                                                import re
                                                text = re.sub(r'<[^>]+>', '', text).strip()
                                                
                                                # Skip command outputs  
                                                if "is running" in text and "…" in text:
                                                    continue
                                                
                                                # Handle image references - extract text after them
                                                if text.startswith("[Image #"):
                                                    parts = text.split("]", 1)
                                                    if len(parts) > 1:
                                                        text = parts[1].strip()
                                                
                                                # If we have real user text, use it
                                                if text and len(text) > 3:  # Lower threshold to catch "hello"
                                                    first_user_msg = text[:100].replace('\n', ' ')
                                                    break
                                    
                                    # Handle string content (less common but possible)
                                    elif isinstance(content, str):
                                        import re
                                        content = content.strip()
                                        
                                        # Remove XML-like tags
                                        content = re.sub(r'<[^>]+>', '', content).strip()
                                        
                                        # Skip command outputs
                                        if "is running" in content and "…" in content:
                                            continue
                                        
                                        # Skip Claude's session continuation messages
                                        if "session is being continued" in content.lower():
                                            continue
                                        
                                        # Skip tool results and interruptions
                                        if not content.startswith("tool_use_id") and "[Request interrupted" not in content:
                                            if content and len(content) > 3:  # Lower threshold to catch short messages
                                                first_user_msg = content[:100].replace('\n', ' ')
                        except json.JSONDecodeError:
                            continue
                            
            return first_user_msg or "No preview available", msg_count
        except Exception as e:
            return f"Error: {str(e)[:30]}", 0

    def list_recent_sessions(self, limit: int = None) -> List[Path]:
        """List recent sessions with details."""
        sessions = self.find_sessions()

        if not sessions:
            print("❌ No Claude sessions found in ~/.claude/projects/")
            print("💡 Make sure you've used Claude Code and have conversations saved.")
            return []

        print(f"\n📚 Found {len(sessions)} Claude sessions:\n")
        print("=" * 80)

        # Show all sessions if no limit specified
        sessions_to_show = sessions[:limit] if limit else sessions
        for i, session in enumerate(sessions_to_show, 1):
            # Clean up project name (remove hyphens, make readable)
            project = session.parent.name.replace('-', ' ').strip()
            if project.startswith("Users"):
                project = "~/" + "/".join(project.split()[2:]) if len(project.split()) > 2 else "Home"
            
            session_id = session.stem
            modified = datetime.fromtimestamp(session.stat().st_mtime)

            # Get file size
            size = session.stat().st_size
            size_kb = size / 1024
            
            # Get preview and message count
            preview, msg_count = self.get_conversation_preview(session)
            
            # Get metadata for slug and subagents
            metadata = self.extract_session_metadata(session)

            # Print formatted info
            print(f"\n{i}. 📁 {project}")
            if metadata["custom_title"]:
                print(f"   🏷️  Title: {metadata['custom_title']}")
            print(f"   📄 Session: {session_id[:8]}...")
            print(f"   📅 Modified: {modified.strftime('%Y-%m-%d %H:%M')}")
            print(f"   💬 Messages: {msg_count}")
            print(f"   💾 Size: {size_kb:.1f} KB")
            if metadata["models"]:
                print(f"   🧠 Models: {', '.join(metadata['models'])}")
            if metadata["has_subagents"]:
                print(f"   🤖 Subagents: {metadata['subagent_count']}")
            print(f"   📝 Preview: \"{preview}...\"")
            print(f"   📎 Output: {self.generate_filename(session)}")

        print("\n" + "=" * 80)
        return sessions[:limit]

    def extract_multiple(
        self, sessions: List[Path], indices: List[int], 
        format: str = "markdown", detailed: bool = False,
        include_subagents: bool = True
    ) -> Tuple[int, int]:
        """Extract multiple sessions by index.
        
        Args:
            sessions: List of session paths
            indices: Indices to extract
            format: Output format ('markdown', 'json', 'html')
            detailed: If True, include tool use and system messages
            include_subagents: If True (default), also extract subagent conversations
        """
        success = 0
        skipped = 0
        total = len(indices)

        for idx in indices:
            if 0 <= idx < len(sessions):
                session_path = sessions[idx]
                conversation = self.extract_conversation(session_path, detailed=detailed)
                if conversation:
                    output_path = self.save_conversation(
                        conversation, session_path.stem,
                        format=format, session_path=session_path
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
                                        sa_conversation, sa_path.stem,
                                        format=format, filename_override=sa_filename
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


def main():
    parser = argparse.ArgumentParser(
        description="Extract Claude Code conversations to clean markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                    # List all available sessions
  %(prog)s --extract 1               # Extract the most recent session
  %(prog)s --extract 1,3,5           # Extract specific sessions
  %(prog)s --recent 5                # Extract 5 most recent sessions
  %(prog)s --all                     # Extract all sessions
  %(prog)s --output ~/my-logs        # Specify output directory
  %(prog)s --search "python error"   # Search conversations
  %(prog)s --search-regex "import.*" # Search with regex
  %(prog)s --format json --all       # Export all as JSON
  %(prog)s --format html --extract 1 # Export session 1 as HTML
  %(prog)s --detailed --extract 1    # Include tool use & system messages
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
        "--limit", type=int, help="Limit for --list command (default: show all)", default=None
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
        help="Output format for exported conversations (default: markdown)"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Include tool use, MCP responses, and system messages in export"
    )
    parser.add_argument(
        "--no-subagents",
        action="store_true",
        help="Exclude subagent (task) conversations from extraction"
    )

    args = parser.parse_args()

    # Handle interactive mode
    if args.interactive or (args.export and args.export.lower() == "logs"):
        from interactive_ui import main as interactive_main

        interactive_main()
        return

    # Initialize extractor with optional output directory
    extractor = ClaudeConversationExtractor(args.output)

    # Handle search mode
    if args.search or args.search_regex:
        from datetime import datetime

        from search_conversations import ConversationSearcher

        searcher = ConversationSearcher()

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
            print(f"\n{len(file_paths_list)}. 📄 {file_path.parent.name} ({len(file_results)} matches)")
            # Show first match preview
            first = file_results[0]
            print(f"   {first.speaker}: {first.matched_content[:100]}...")

        # Offer to view conversations
        if file_paths_list:
            print("\n" + "=" * 60)
            try:
                view_choice = input("\nView a conversation? Enter number (1-{}) or press Enter to skip: ".format(
                    len(file_paths_list))).strip()
                
                if view_choice.isdigit():
                    view_num = int(view_choice)
                    if 1 <= view_num <= len(file_paths_list):
                        selected_path = file_paths_list[view_num - 1]
                        extractor.display_conversation(selected_path, detailed=args.detailed)
                        
                        # Offer to extract after viewing
                        extract_choice = input("\n📤 Extract this conversation? (y/N): ").strip().lower()
                        if extract_choice == 'y':
                            conversation = extractor.extract_conversation(selected_path, detailed=args.detailed)
                            if conversation:
                                session_id = selected_path.stem
                                output = extractor.save_conversation(
                                    conversation, session_id,
                                    format=args.format, session_path=selected_path
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
            print("  claude-extract --extract <number>      # Extract specific session")
            print("  claude-extract --recent 5              # Extract 5 most recent")
            print("  claude-extract --all                   # Extract all sessions")

    elif args.extract:
        sessions = extractor.find_sessions()

        # Parse comma-separated indices
        indices = []
        for num in args.extract.split(","):
            try:
                idx = int(num.strip()) - 1  # Convert to 0-based index
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
                sessions, indices, format=args.format, detailed=args.detailed,
                include_subagents=not args.no_subagents
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
            sessions, indices, format=args.format, detailed=args.detailed,
            include_subagents=not args.no_subagents
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
            sessions, indices, format=args.format, detailed=args.detailed,
            include_subagents=not args.no_subagents
        )
        print(f"\n✅ Successfully extracted {success}/{total} sessions")


def launch_interactive():
    """Launch the interactive UI directly, or handle search if specified."""
    import sys
    
    # If no arguments provided, launch interactive UI
    if len(sys.argv) == 1:
        try:
            from .interactive_ui import main as interactive_main
        except ImportError:
            from interactive_ui import main as interactive_main
        interactive_main()
    # Check if 'search' was passed as an argument
    elif len(sys.argv) > 1 and sys.argv[1] == 'search':
        # Launch real-time search with viewing capability
        try:
            from .realtime_search import RealTimeSearch, create_smart_searcher
            from .search_conversations import ConversationSearcher
        except ImportError:
            from realtime_search import RealTimeSearch, create_smart_searcher
            from search_conversations import ConversationSearcher
        
        # Initialize components
        extractor = ClaudeConversationExtractor()
        searcher = ConversationSearcher()
        smart_searcher = create_smart_searcher(searcher)
        
        # Run search
        rts = RealTimeSearch(smart_searcher, extractor)
        selected_file = rts.run()
        
        if selected_file:
            # View the selected conversation
            extractor.display_conversation(selected_file)
            
            # Offer to extract
            try:
                extract_choice = input("\n📤 Extract this conversation? (y/N): ").strip().lower()
                if extract_choice == 'y':
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
