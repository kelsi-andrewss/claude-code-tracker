#!/usr/bin/env python3
"""Export tracking.db to JSON files for portability.

Usage: python3 export-json.py [<tracking_dir>]
Defaults to .claude/tracking/ in the current git root.
"""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import storage

def find_tracking_dir():
    root = os.getcwd()
    while root != "/":
        if os.path.exists(os.path.join(root, ".git")):
            return os.path.join(root, ".claude", "tracking")
        root = os.path.dirname(root)
    return os.path.join(os.getcwd(), ".claude", "tracking")

tracking_dir = sys.argv[1] if len(sys.argv) > 1 else find_tracking_dir()

if not os.path.exists(os.path.join(tracking_dir, "tracking.db")):
    sys.exit(f"No tracking.db found in {tracking_dir}")

storage.export_json(tracking_dir)
print(f"Exported to {tracking_dir}/tokens.json and agents.json")
