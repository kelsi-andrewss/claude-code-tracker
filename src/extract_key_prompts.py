#!/usr/bin/env python3
"""
Extract non-trivial human prompts from JSONL transcripts and write to
key-prompts/YYYY-MM-DD.md files.

Uses the same filtering logic as generate-charts.py:
  - Human messages only (type="user", not sidechain)
  - Skip tool-result-only messages (content starting with "<")
  - Skip slash commands
  - "Trivial" = len < 40 and no "?" — these are skipped
  - Everything else is a key prompt

Called by both backfill.py (historical) and parse-session.py (live sessions).
"""
import json
import os
import re
from datetime import datetime


def _is_trivial(text):
    """Match generate-charts.py trivial classification exactly."""
    return len(text) < 40 and "?" not in text


def _extract_text(obj):
    """Extract human-readable text from a JSONL user message object.

    Returns the text string or None if the message should be skipped.
    """
    content = obj.get("message", {}).get("content", "")
    if isinstance(content, list):
        texts = [
            c.get("text", "") for c in content
            if isinstance(c, dict) and c.get("type") == "text"
            and not str(c.get("text", "")).strip().startswith("<")
        ]
        if texts:
            return " ".join(texts).strip()
        return None
    elif isinstance(content, str):
        text = content.strip()
        if text and not text.startswith("<") and not text.startswith("/"):
            return text
    return None


def extract_prompts_from_jsonl(jsonl_path, session_id):
    """Read a JSONL transcript and return a list of key prompt dicts.

    Each dict has: date, time_str, text, session_id
    Only non-trivial human messages are included.
    """
    prompts = []

    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)

                    if obj.get("type") != "user":
                        continue
                    if obj.get("userType") not in ("human", "external", None):
                        continue
                    if obj.get("isSidechain"):
                        continue

                    text = _extract_text(obj)
                    if not text:
                        continue
                    if _is_trivial(text):
                        continue

                    # Parse timestamp
                    ts = obj.get("timestamp", "")
                    prompt_date = None
                    time_str = ""
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            prompt_date = dt.strftime("%Y-%m-%d")
                            time_str = dt.strftime("%H:%M")
                        except Exception:
                            pass

                    prompts.append({
                        "date": prompt_date,
                        "time_str": time_str,
                        "text": text,
                        "session_id": session_id,
                    })
                except Exception:
                    pass
    except Exception:
        pass

    return prompts


def _categorize_prompt(text):
    """Auto-categorize a prompt based on content heuristics.

    Matches the 4 original categories:
      breakthrough, bug-resolution, architecture, feature
    """
    lower = text.lower()

    # Bug-resolution signals
    bug_signals = [
        "bug", "fix", "error", "crash", "broken", "fail", "issue",
        "wrong", "doesn't work", "not working", "debug", "stack trace",
        "exception", "undefined", "null", "typo", "regression",
    ]
    if any(s in lower for s in bug_signals):
        return "bug-resolution"

    # Architecture signals
    arch_signals = [
        "architect", "design", "refactor", "restructur", "pattern",
        "migration", "schema", "database", "infrastructure", "deploy",
        "ci/cd", "pipeline", "monorepo", "microservice", "scaling",
        "plan", "approach", "strategy", "trade-off", "tradeoff",
    ]
    if any(s in lower for s in arch_signals):
        return "architecture"

    # Breakthrough — long detailed prompts or ones with strong directive language
    if len(text) > 500:
        return "breakthrough"

    # Default
    return "feature"


def write_key_prompts(tracking_dir, prompts):
    """Write prompts to key-prompts/YYYY-MM-DD.md files.

    Groups prompts by date, appends to existing files (avoiding duplicates),
    and uses the original intended format with **Category** tags.

    Returns the number of new entries written.
    """
    if not prompts:
        return 0

    prompts_dir = os.path.join(tracking_dir, "key-prompts")
    os.makedirs(prompts_dir, exist_ok=True)

    # Group by date
    by_date = {}
    for p in prompts:
        d = p.get("date")
        if not d:
            continue
        by_date.setdefault(d, []).append(p)

    total_written = 0

    for date_str, day_prompts in sorted(by_date.items()):
        file_path = os.path.join(prompts_dir, f"{date_str}.md")

        # Load existing content to detect duplicates
        existing_content = ""
        if os.path.exists(file_path):
            try:
                with open(file_path, encoding="utf-8") as f:
                    existing_content = f.read()
            except Exception:
                pass

        # Determine next entry number from existing content
        existing_nums = re.findall(r'^## .+? — ', existing_content, re.MULTILINE)
        next_num = len(existing_nums) + 1

        # Build new entries, skipping duplicates
        new_entries = []
        for p in day_prompts:
            # Truncate for duplicate check — first 80 chars of prompt text
            snippet = p["text"][:80]
            if snippet in existing_content:
                continue

            category = _categorize_prompt(p["text"])
            time_label = p.get("time_str", "")
            session_short = p["session_id"][:8] if p.get("session_id") else ""

            # Truncate very long prompts for the entry (keep full in quote block)
            title = p["text"][:80].replace("\n", " ")
            if len(p["text"]) > 80:
                title += "..."

            entry = f"## [{time_label}] — {title}\n"
            entry += f"**Category**: {category}\n"
            entry += f"**Context**: Session `{session_short}...`\n"
            entry += f"**The Prompt**:\n> {p['text']}\n\n"

            new_entries.append(entry)
            next_num += 1

        if not new_entries:
            continue

        # Write: create file with header if new, or append
        if not existing_content:
            header = f"# Key Prompts — {date_str}\n\n"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(header)
                for entry in new_entries:
                    f.write(entry)
        else:
            with open(file_path, "a", encoding="utf-8") as f:
                for entry in new_entries:
                    f.write(entry)

        total_written += len(new_entries)

    return total_written
