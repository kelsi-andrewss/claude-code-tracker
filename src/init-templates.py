#!/usr/bin/env python3
"""Cross-platform replacement for init-templates.sh."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <tracking_dir>", file=sys.stderr)
        sys.exit(1)

    tracking_dir = sys.argv[1]
    os.makedirs(tracking_dir, exist_ok=True)

    # Initialize SQLite database (replaces tokens.json / agents.json)
    storage.init_db(tracking_dir)

    # Create key-prompts directory
    key_prompts_dir = os.path.join(tracking_dir, 'key-prompts')
    os.makedirs(key_prompts_dir, exist_ok=True)

if __name__ == '__main__':
    main()
