#!/usr/bin/env python3
"""
Usage:
  python3 cost-summary.py <tokens.json>
  python3 cost-summary.py  (defaults to .claude/tracking/tokens.json in cwd's git root)
"""
import sys
import json
import os
from collections import defaultdict
from datetime import date

def find_tokens_file():
    cwd = os.getcwd()
    root = cwd
    while root != "/":
        if os.path.isdir(os.path.join(root, ".git")):
            break
        root = os.path.dirname(root)
    path = os.path.join(root, ".claude", "tracking", "tokens.json")
    if os.path.exists(path):
        return path
    sys.exit(f"No tokens.json found at {path}")

tokens_file = sys.argv[1] if len(sys.argv) > 1 else find_tokens_file()

with open(tokens_file) as f:
    data = json.load(f)

if not data:
    print("No sessions recorded yet.")
    sys.exit(0)

# --- Aggregate ---
by_date = defaultdict(lambda: {"cost": 0, "sessions": 0, "output": 0, "cache_read": 0, "cache_create": 0, "input": 0})
by_model = defaultdict(lambda: {"cost": 0, "sessions": 0})
total_cost = 0
total_sessions = len(data)
sessions_with_tokens = 0

for e in data:
    d = e.get("date", "unknown")
    cost = e.get("estimated_cost_usd", 0)
    model = e.get("model", "unknown")
    short_model = model.split("-20")[0] if "-20" in model else model

    by_date[d]["cost"] += cost
    by_date[d]["sessions"] += 1
    by_date[d]["output"] += e.get("output_tokens", 0)
    by_date[d]["cache_read"] += e.get("cache_read_tokens", 0)
    by_date[d]["cache_create"] += e.get("cache_creation_tokens", 0)
    by_date[d]["input"] += e.get("input_tokens", 0)

    by_model[short_model]["cost"] += cost
    by_model[short_model]["sessions"] += 1

    total_cost += cost
    if e.get("total_tokens", 0) > 0:
        sessions_with_tokens += 1

total_output = sum(e.get("output_tokens", 0) for e in data)
total_cache_read = sum(e.get("cache_read_tokens", 0) for e in data)
total_cache_create = sum(e.get("cache_creation_tokens", 0) for e in data)
total_input = sum(e.get("input_tokens", 0) for e in data)

# --- Print ---
W = 60
print("=" * W)
print(f"  Cost Summary — {os.path.basename(os.path.dirname(os.path.dirname(tokens_file)))}")
print("=" * W)

print(f"\nBy date:")
print(f"  {'Date':<12} {'Sessions':>8} {'Output':>10} {'Cache Read':>12} {'Cost':>10}")
print(f"  {'-'*12} {'-'*8} {'-'*10} {'-'*12} {'-'*10}")
for d in sorted(by_date):
    r = by_date[d]
    print(f"  {d:<12} {r['sessions']:>8} {r['output']:>10,} {r['cache_read']:>12,} ${r['cost']:>9.2f}")

print(f"\nBy model:")
print(f"  {'Model':<30} {'Sessions':>8} {'Cost':>10}")
print(f"  {'-'*30} {'-'*8} {'-'*10}")
for m in sorted(by_model, key=lambda x: -by_model[x]["cost"]):
    r = by_model[m]
    print(f"  {m:<30} {r['sessions']:>8} ${r['cost']:>9.2f}")

print(f"\nTotals:")
print(f"  Sessions:          {total_sessions:>8}  ({sessions_with_tokens} with token data)")
print(f"  Input tokens:      {total_input:>12,}")
print(f"  Cache write:       {total_cache_create:>12,}")
print(f"  Cache read:        {total_cache_read:>12,}")
print(f"  Output tokens:     {total_output:>12,}")
print(f"  Estimated cost:    ${total_cost:>11.2f}")

if total_output > 0:
    cache_pct = total_cache_read / (total_input + total_cache_create + total_cache_read + total_output) * 100
    print(f"  Cache read share:  {cache_pct:>10.1f}%  of all tokens")

days = len(by_date)
if days > 1:
    print(f"\n  Avg cost/day:      ${total_cost/days:>11.2f}  over {days} days")

print("=" * W)
