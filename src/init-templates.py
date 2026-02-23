#!/usr/bin/env python3
"""
Initialise a tracking directory with template files.

Usage:
    python init-templates.py <tracking_dir>

Cross-platform replacement for init-templates.sh.
"""
import sys
import os
from datetime import date


def main():
    tracking_dir = sys.argv[1]
    os.makedirs(tracking_dir, exist_ok=True)
    os.makedirs(os.path.join(tracking_dir, "key-prompts"), exist_ok=True)

    templates = {
        "tokens.json": "[]",
        "key-prompts.md": (
            "# Prompt Journal\n"
            "\n"
            "High-signal prompts organized by day.\n"
            "\n"
            "| File | Entries | Highlights |\n"
            "|------|---------|------------|\n"
            "\n"
            "**Total**: 0 entries\n"
            "\n"
            "---\n"
            "\n"
            "New entries go in `key-prompts/YYYY-MM-DD.md` for today's date. "
            "Create the file if it doesn't exist \u2014 use the same header "
            "format as existing files.\n"
        ),
        "sessions.md": (
            "# Session Log\n"
            "\n"
            "---\n"
        ),
        "cost-analysis.md": (
            "# AI Cost Analysis\n"
            "\n"
            "## Development Costs\n"
            "\n"
            "| Date | Session Summary | Input | Cache Write | Cache Read | Output | Cost (USD) |\n"
            "|------|----------------|-------|-------------|------------|--------|------------|\n"
            "| | **Total** | | | | | **$0.00** |\n"
            "\n"
            "*Token counts include prompt caching. Pricing: Sonnet 4.5 -- "
            "input $3/M, cache write $3.75/M, cache read $0.30/M, output $15/M. "
            "Opus 4.6 -- input $15/M, cache write $18.75/M, cache read $1.50/M, "
            "output $75/M.*\n"
            "\n"
            "---\n"
            "\n"
            "## Anthropic Pricing Reference\n"
            "\n"
            "| Model | Input (per M) | Output (per M) | Cache Write | Cache Read |\n"
            "|-------|--------------|----------------|-------------|------------|\n"
            "| Claude Opus 4.6 | $15.00 | $75.00 | $18.75 | $1.50 |\n"
            "| Claude Sonnet 4.5 | $3.00 | $15.00 | $3.75 | $0.30 |\n"
            "| Claude Haiku 4.5 | $0.80 | $4.00 | $1.00 | $0.08 |\n"
        ),
        "ai-dev-log.md": (
            "# AI Development Log\n"
            "\n"
            f"**Period**: Started {date.today().isoformat()}\n"
            "**Primary AI Tool**: Claude Code\n"
            "\n"
            "---\n"
            "\n"
            "## Tools & Workflow\n"
            "\n"
            "*Document your AI workflow here.*\n"
            "\n"
            "---\n"
            "\n"
            "## Effective Prompts\n"
            "\n"
            "See `key-prompts.md` for the full journal with context and analysis.\n"
            "\n"
            "---\n"
            "\n"
            "## Code Analysis\n"
            "\n"
            "*Document AI contribution estimates here.*\n"
            "\n"
            "---\n"
            "\n"
            "## Key Learnings\n"
            "\n"
            "*Document key learnings as you go.*\n"
        ),
    }

    for filename, content in templates.items():
        filepath = os.path.join(tracking_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)


if __name__ == "__main__":
    main()
