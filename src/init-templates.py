#!/usr/bin/env python3
"""Cross-platform replacement for init-templates.sh."""
import sys
import json
import os

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <tracking_dir>", file=sys.stderr)
        sys.exit(1)

    tracking_dir = sys.argv[1]
    os.makedirs(tracking_dir, exist_ok=True)

    templates = {
        'tokens.json': [],
        'agents.json': [],
        'friction.json': [],
    }

    for filename, default in templates.items():
        filepath = os.path.join(tracking_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default, f, indent=2)
                f.write('\n')
            print(f"Created {filepath}")
        else:
            print(f"Skipped {filepath} (already exists)")

    # Create key-prompts directory
    key_prompts_dir = os.path.join(tracking_dir, 'key-prompts')
    os.makedirs(key_prompts_dir, exist_ok=True)

if __name__ == '__main__':
    main()
