#!/usr/bin/env python3
"""
Generates tracking/charts.html from tokens.json + key-prompts/ folder.
Called by stop-hook.sh after each session update.

Usage: python3 generate-charts.py <tokens.json> <output.html>
"""
import sys, json, os, re, glob
from collections import defaultdict

tokens_file = sys.argv[1]
output_file = sys.argv[2]

def format_duration(seconds):
    if seconds <= 0:
        return "0m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {s}s"

with open(tokens_file) as f:
    data = json.load(f)

if not data:
    sys.exit(0)

# --- Aggregate by date ---
# Each entry is a turn; group by date for bar charts, session_id for unique session count
by_date = defaultdict(lambda: {"cost": 0, "turns": 0, "output": 0,
                                "cache_read": 0, "cache_create": 0, "input": 0,
                                "opus_cost": 0, "sonnet_cost": 0, "duration": 0})
by_model = defaultdict(lambda: {"cost": 0, "turns": 0})
cumulative = []

running_cost = 0
running_duration = 0
sort_key = lambda x: (x.get("date", ""), x.get("session_id", ""), x.get("turn_index", 0))
for e in sorted(data, key=sort_key):
    d = e.get("date", "unknown")
    cost = e.get("estimated_cost_usd", 0)
    model = e.get("model", "unknown")
    short = model.split("-20")[0] if "-20" in model else model

    by_date[d]["cost"] += cost
    by_date[d]["turns"] += 1
    by_date[d]["output"] += e.get("output_tokens", 0)
    by_date[d]["cache_read"] += e.get("cache_read_tokens", 0)
    by_date[d]["cache_create"] += e.get("cache_creation_tokens", 0)
    by_date[d]["input"] += e.get("input_tokens", 0)
    if "opus" in model:
        by_date[d]["opus_cost"] += cost
    else:
        by_date[d]["sonnet_cost"] += cost
    by_date[d]["duration"] += e.get("duration_seconds", 0)

    by_model[short]["cost"] += cost
    by_model[short]["turns"] += 1

    running_cost += cost
    running_duration += e.get("duration_seconds", 0)
    cumulative.append({"date": d, "cumulative_cost": round(running_cost, 4),
                        "cumulative_duration": round(running_duration),
                        "session_id": e.get("session_id", "")[:8],
                        "turn_index": e.get("turn_index", 0)})

dates = sorted(by_date.keys())
total_cost = sum(e.get("estimated_cost_usd", 0) for e in data)
total_turns = len(data)
total_sessions = len({e.get("session_id") for e in data})
sessions_with_data = len({e.get("session_id") for e in data if e.get("total_tokens", 0) > 0})
total_output = sum(e.get("output_tokens", 0) for e in data)
total_cache_read = sum(e.get("cache_read_tokens", 0) for e in data)
total_all_tokens = sum(e.get("total_tokens", 0) for e in data)
cache_pct = round(total_cache_read / total_all_tokens * 100, 1) if total_all_tokens > 0 else 0
total_duration = sum(e.get("duration_seconds", 0) for e in data)
avg_duration = total_duration // total_turns if total_turns > 0 else 0

project_name = data[0].get("project", "Project") if data else "Project"

# --- Count total human messages per date from JSONL transcripts ---
project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(tokens_file))))  # project root
# Claude Code slugifies paths as: replace every "/" with "-" (keeping leading slash → leading dash)
transcripts_dir = os.path.expanduser(
    "~/.claude/projects/" + project_dir.replace("/", "-")
)
human_by_date = defaultdict(int)
trivial_by_date = defaultdict(int)

def _is_trivial(text):
    return len(text) < 40 and "?" not in text

if os.path.isdir(transcripts_dir):
    for jf in glob.glob(os.path.join(transcripts_dir, "*.jsonl")):
        # Use session date from tokens.json if available, else file mtime
        sid = os.path.splitext(os.path.basename(jf))[0]
        session_date = None
        for e in data:
            if e.get("session_id") == sid:
                session_date = e.get("date")
                break
        if not session_date:
            import datetime
            session_date = datetime.datetime.fromtimestamp(
                os.path.getmtime(jf)).strftime("%Y-%m-%d")

        try:
            with open(jf) as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        # Human messages have type="user" and userType="human" at the top level
                        if obj.get("type") != "user":
                            continue
                        if obj.get("userType") not in ("human", "external", None):
                            continue
                        if obj.get("isSidechain"):
                            continue
                        content = obj.get("message", {}).get("content", "")
                        if isinstance(content, list):
                            # Skip pure tool-result messages
                            texts = [
                                c.get("text", "") for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                                and not str(c.get("text", "")).strip().startswith("<")
                            ]
                            if texts:
                                text = " ".join(texts).strip()
                                human_by_date[session_date] += 1
                                if _is_trivial(text):
                                    trivial_by_date[session_date] += 1
                        elif isinstance(content, str):
                            text = content.strip()
                            # Skip slash commands and empty
                            if text and not text.startswith("<") and not text.startswith("/"):
                                human_by_date[session_date] += 1
                                if _is_trivial(text):
                                    trivial_by_date[session_date] += 1
                    except:
                        pass
        except:
            pass

total_human_msgs = sum(human_by_date.values())
total_trivial_msgs = sum(trivial_by_date.values())

# --- Aggregate prompt data from key-prompts/ folder ---
prompts_dir = os.path.join(os.path.dirname(tokens_file), "key-prompts")
prompt_files = sorted(glob.glob(os.path.join(prompts_dir, "????-??-??.md")))

prompt_by_date = {}   # date -> {total, by_category}
all_categories = set()

for f in prompt_files:
    date = os.path.splitext(os.path.basename(f))[0]
    content = open(f).read()
    cats = re.findall(r'^\*\*Category\*\*: (\S+)', content, re.MULTILINE)
    by_cat = defaultdict(int)
    for c in cats:
        by_cat[c] += 1
        all_categories.add(c)
    prompt_by_date[date] = {"total": len(cats), "by_category": dict(by_cat)}

all_categories = sorted(all_categories)
prompt_dates = sorted(prompt_by_date.keys())
total_prompts = sum(v["total"] for v in prompt_by_date.values())

# Build JS data structures
dates_js = json.dumps(dates)
cost_by_date_js = json.dumps([round(by_date[d]["cost"], 4) for d in dates])
sessions_by_date_js = json.dumps([by_date[d]["turns"] for d in dates])
output_by_date_js = json.dumps([by_date[d]["output"] for d in dates])
cache_read_by_date_js = json.dumps([by_date[d]["cache_read"] for d in dates])
opus_by_date_js = json.dumps([round(by_date[d]["opus_cost"], 4) for d in dates])
sonnet_by_date_js = json.dumps([round(by_date[d]["sonnet_cost"], 4) for d in dates])
duration_by_date_js = json.dumps([by_date[d]["duration"] for d in dates])

cumul_labels_js = json.dumps([f"{c['date']} {c['session_id']}#{c['turn_index']}" for c in cumulative])
cumul_values_js = json.dumps([c["cumulative_cost"] for c in cumulative])
cumul_duration_js = json.dumps([c["cumulative_duration"] for c in cumulative])

avg_duration_by_date_js = json.dumps([
    round(by_date[d]["duration"] / by_date[d]["turns"])
    if by_date[d]["turns"] > 0 else 0
    for d in dates
])

scatter_data_js = json.dumps([
    {"x": e.get("duration_seconds", 0),
     "y": round(e.get("estimated_cost_usd", 0), 4),
     "label": f"{e.get('date', '')} {e.get('session_id', '')[:6]}#{e.get('turn_index', 0)}"}
    for e in sorted(data, key=sort_key)
    if e.get("duration_seconds", 0) > 0
])

# Tokens per minute per turn (output tokens / duration in minutes)
tpm_data_js = json.dumps([
    {"x": e.get("duration_seconds", 0),
     "y": round(e.get("output_tokens", 0) / (e["duration_seconds"] / 60), 1),
     "label": f"{e.get('date', '')} {e.get('session_id', '')[:6]}#{e.get('turn_index', 0)}"}
    for e in sorted(data, key=sort_key)
    if e.get("duration_seconds", 0) > 0 and e.get("output_tokens", 0) > 0
])

# Duration histogram: bucket turns into ranges
_dur_buckets = [("<5s", 0, 5), ("5–15s", 5, 15), ("15–30s", 15, 30),
                ("30s–2m", 30, 120), ("2m+", 120, None)]
_dur_counts = {label: 0 for label, _, _ in _dur_buckets}
for e in data:
    d = e.get("duration_seconds", 0)
    if d <= 0:
        continue
    for label, lo, hi in _dur_buckets:
        if hi is None or d < hi:
            _dur_counts[label] += 1
            break
dur_hist_labels_js = json.dumps([b[0] for b in _dur_buckets])
dur_hist_values_js = json.dumps([_dur_counts[b[0]] for b in _dur_buckets])

model_labels_js = json.dumps(list(by_model.keys()))
model_costs_js = json.dumps([round(by_model[m]["cost"], 4) for m in by_model])
model_sessions_js = json.dumps([by_model[m]["turns"] for m in by_model])

# All dates union for prompts vs total chart
all_prompt_dates = sorted(set(list(prompt_by_date.keys()) + list(human_by_date.keys())))
all_prompt_dates_js = json.dumps(all_prompt_dates)
total_msgs_by_date_js = json.dumps([human_by_date.get(d, 0) for d in all_prompt_dates])
trivial_by_date_js = json.dumps([trivial_by_date.get(d, 0) for d in all_prompt_dates])
key_prompts_by_date_js = json.dumps([prompt_by_date.get(d, {}).get("total", 0) for d in all_prompt_dates])

# Efficiency ratio per date: key / (total - trivial) * 100, None if no non-trivial messages
efficiency_by_date = []
for d in all_prompt_dates:
    total = human_by_date.get(d, 0)
    trivial = trivial_by_date.get(d, 0)
    non_trivial = total - trivial
    key = prompt_by_date.get(d, {}).get("total", 0)
    efficiency_by_date.append(round(key / non_trivial * 100, 1) if non_trivial > 0 else None)
efficiency_by_date_js = json.dumps(efficiency_by_date)

non_trivial_total = total_human_msgs - total_trivial_msgs
overall_efficiency = round(total_prompts / non_trivial_total * 100, 1) if non_trivial_total > 0 else 0

# Prompt chart data
prompt_dates_js = json.dumps(prompt_dates)
prompt_totals_js = json.dumps([prompt_by_date[d]["total"] for d in prompt_dates])

CAT_COLORS = {
    "bug-resolution": "#f87171",
    "architecture":   "#6366f1",
    "feature":        "#34d399",
    "breakthrough":   "#f59e0b",
}
DEFAULT_COLOR = "#94a3b8"

cat_datasets = []
for cat in all_categories:
    cat_datasets.append({
        "label": cat,
        "data": [prompt_by_date[d]["by_category"].get(cat, 0) for d in prompt_dates],
        "backgroundColor": CAT_COLORS.get(cat, DEFAULT_COLOR),
        "borderRadius": 2,
    })
cat_datasets_js = json.dumps(cat_datasets)

# Category totals for doughnut
cat_totals = {c: sum(prompt_by_date[d]["by_category"].get(c, 0) for d in prompt_dates)
              for c in all_categories}
donut_labels_js = json.dumps(list(cat_totals.keys()))
donut_values_js = json.dumps(list(cat_totals.values()))
donut_colors_js = json.dumps([CAT_COLORS.get(c, DEFAULT_COLOR) for c in cat_totals])

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code — {project_name} tracking</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0f1117; color: #e2e8f0; padding: 24px; }}
  h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 4px; color: #f8fafc; }}
  .subtitle {{ font-size: 0.8rem; color: #64748b; margin-bottom: 24px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
             gap: 12px; margin-bottom: 28px; }}
  .stat {{ background: #1e2330; border: 1px solid #2d3748; border-radius: 10px;
           padding: 14px 16px; }}
  .stat-label {{ font-size: 0.7rem; color: #64748b; text-transform: uppercase;
                  letter-spacing: 0.05em; margin-bottom: 4px; }}
  .stat-value {{ font-size: 1.4rem; font-weight: 700; color: #f8fafc; }}
  .stat-sub {{ font-size: 0.7rem; color: #94a3b8; margin-top: 2px; }}
  .section {{ margin-bottom: 36px; }}
  .section-header {{ font-size: 0.75rem; font-weight: 600; color: #64748b;
                     text-transform: uppercase; letter-spacing: 0.08em;
                     padding: 0 0 10px 12px; margin-bottom: 16px;
                     border-bottom: 1px solid #2d3748; }}
  .section-header.cost  {{ border-left: 3px solid #6366f1; color: #818cf8; }}
  .section-header.time  {{ border-left: 3px solid #34d399; color: #34d399; }}
  .section-header.prompts {{ border-left: 3px solid #a78bfa; color: #a78bfa; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .card {{ background: #1e2330; border: 1px solid #2d3748; border-radius: 10px;
           padding: 16px; }}
  .card.wide {{ grid-column: 1 / -1; }}
  .card h2 {{ font-size: 0.78rem; font-weight: 600; color: #94a3b8;
               text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 14px; }}
  canvas {{ max-height: 240px; }}
  .wide canvas {{ max-height: 200px; }}
  .notice {{ font-size: 0.78rem; color: #94a3b8; background: #1e2330;
             border: 1px solid #3b4a6b; border-left: 3px solid #6366f1;
             border-radius: 6px; padding: 10px 14px; margin-bottom: 20px; }}
  .notice strong {{ color: #e2e8f0; }}
  @media (max-width: 700px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>Claude Code — {project_name}</h1>
<p class="subtitle">Updated after every session &mdash; open in browser to view</p>
<p class="notice">&#9432; Cost figures are <strong>API list-price equivalents</strong> (what pay-as-you-go API customers would be charged). If you are on a Max subscription, these are <em>not</em> amounts billed to you.</p>

<div class="stats">
  <div class="stat">
    <div class="stat-label">API list-price equivalent</div>
    <div class="stat-value">${total_cost:.2f}</div>
    <div class="stat-sub">across {len(dates)} day{"s" if len(dates) != 1 else ""} (not billed)</div>
  </div>
  <div class="stat">
    <div class="stat-label">Sessions</div>
    <div class="stat-value">{total_sessions}</div>
    <div class="stat-sub">{total_turns} prompts total</div>
  </div>
  <div class="stat">
    <div class="stat-label">Output tokens</div>
    <div class="stat-value">{total_output:,}</div>
    <div class="stat-sub">&nbsp;</div>
  </div>
  <div class="stat">
    <div class="stat-label">Cache read share</div>
    <div class="stat-value">{cache_pct}%</div>
    <div class="stat-sub">of all tokens</div>
  </div>
  <div class="stat">
    <div class="stat-label">Active time</div>
    <div class="stat-value">{format_duration(total_duration)}</div>
    <div class="stat-sub">avg {format_duration(avg_duration)} / prompt</div>
  </div>
  <div class="stat">
    <div class="stat-label">Key prompts captured</div>
    <div class="stat-value">{total_prompts}</div>
    <div class="stat-sub">of {total_human_msgs:,} total prompts</div>
  </div>
  <div class="stat">
    <div class="stat-label">Prompt efficiency</div>
    <div class="stat-value">{overall_efficiency}%</div>
    <div class="stat-sub">key / non-trivial (higher = better)</div>
  </div>
</div>

<div class="section">
  <div class="section-header cost">Cost &amp; Usage</div>
  <div class="grid">

    <div class="card wide">
      <h2>Cumulative cost</h2>
      <canvas id="cumul"></canvas>
    </div>

    <div class="card">
      <h2>Cost per day</h2>
      <canvas id="costDay"></canvas>
    </div>

    <div class="card">
      <h2>Prompts per day</h2>
      <canvas id="sessDay"></canvas>
    </div>

    <div class="card wide">
      <h2>Cost by model</h2>
      <canvas id="modelStack"></canvas>
    </div>

  </div>
</div>

<div class="section">
  <div class="section-header prompts">Key Prompts</div>
  <div class="grid">

    <div class="card wide">
      <h2>Prompts per day</h2>
      <canvas id="promptsVsTotal"></canvas>
    </div>

    <div class="card">
      <h2>Efficiency per day (%)</h2>
      <canvas id="promptEfficiency"></canvas>
    </div>

    <div class="card">
      <h2>Category breakdown</h2>
      <canvas id="promptDonut"></canvas>
    </div>

    <div class="card wide">
      <h2>Categories per day</h2>
      <canvas id="promptStack"></canvas>
    </div>

  </div>
</div>

<div class="section">
  <div class="section-header time">Time</div>
  <div class="grid">

    <div class="card">
      <h2>Duration per day</h2>
      <canvas id="durationDay"></canvas>
    </div>

    <div class="card">
      <h2>Avg duration per day</h2>
      <canvas id="avgDurationDay"></canvas>
    </div>

    <div class="card">
      <h2>Tokens per minute</h2>
      <canvas id="tokensPerMin"></canvas>
    </div>

    <div class="card">
      <h2>Prompt length distribution</h2>
      <canvas id="durationDist"></canvas>
    </div>

    <div class="card wide">
      <h2>Cumulative time</h2>
      <canvas id="cumulTime"></canvas>
    </div>

    <div class="card wide">
      <h2>Time vs cost</h2>
      <canvas id="timeVsCost"></canvas>
    </div>

  </div>
</div>

<script>
const DATES = {dates_js};
const COST_BY_DATE = {cost_by_date_js};
const SESSIONS_BY_DATE = {sessions_by_date_js};
const OUTPUT_BY_DATE = {output_by_date_js};
const OPUS_BY_DATE = {opus_by_date_js};
const SONNET_BY_DATE = {sonnet_by_date_js};
const CUMUL_LABELS = {cumul_labels_js};
const CUMUL_VALUES = {cumul_values_js};
const MODEL_LABELS = {model_labels_js};
const MODEL_COSTS = {model_costs_js};
const MODEL_SESSIONS = {model_sessions_js};
const PROMPT_DATES = {prompt_dates_js};
const PROMPT_TOTALS = {prompt_totals_js};
const PROMPT_CAT_DATASETS = {cat_datasets_js};
const DONUT_LABELS = {donut_labels_js};
const DONUT_VALUES = {donut_values_js};
const DONUT_COLORS = {donut_colors_js};
const ALL_PROMPT_DATES = {all_prompt_dates_js};
const TOTAL_MSGS_BY_DATE = {total_msgs_by_date_js};
const TRIVIAL_BY_DATE = {trivial_by_date_js};
const KEY_PROMPTS_BY_DATE = {key_prompts_by_date_js};
const EFFICIENCY_BY_DATE = {efficiency_by_date_js};
const DURATION_BY_DATE = {duration_by_date_js};
const CUMUL_DURATION = {cumul_duration_js};
const AVG_DURATION_BY_DATE = {avg_duration_by_date_js};
const SCATTER_DATA = {scatter_data_js};
const TPM_DATA = {tpm_data_js};
const DUR_HIST_LABELS = {dur_hist_labels_js};
const DUR_HIST_VALUES = {dur_hist_values_js};

function formatDuration(s) {{
  if (s <= 0) return '0s';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.round(s % 60);
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm' + (sec > 0 ? ' ' + sec + 's' : '');
  return sec + 's';
}}

const GRID = '#2d3748';
const TEXT = '#94a3b8';
const baseOpts = {{
  responsive: true,
  maintainAspectRatio: true,
  plugins: {{ legend: {{ labels: {{ color: TEXT, boxWidth: 12, font: {{ size: 11 }} }} }} }},
  scales: {{
    x: {{ ticks: {{ color: TEXT, font: {{ size: 10 }} }}, grid: {{ color: GRID }} }},
    y: {{ ticks: {{ color: TEXT, font: {{ size: 10 }} }}, grid: {{ color: GRID }} }}
  }}
}};

// Cumulative cost line
new Chart(document.getElementById('cumul'), {{
  type: 'line',
  data: {{
    labels: CUMUL_LABELS,
    datasets: [{{ label: 'Cumulative cost ($)', data: CUMUL_VALUES,
      borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.15)',
      fill: true, tension: 0.3, pointRadius: 2 }}]
  }},
  options: {{ ...baseOpts, plugins: {{ ...baseOpts.plugins,
    tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.y.toFixed(2) }} }} }} }}
}});

// Cost per day bar
new Chart(document.getElementById('costDay'), {{
  type: 'bar',
  data: {{
    labels: DATES,
    datasets: [{{ label: 'Cost ($)', data: COST_BY_DATE,
      backgroundColor: '#6366f1', borderRadius: 4 }}]
  }},
  options: {{ ...baseOpts, plugins: {{ ...baseOpts.plugins,
    tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.y.toFixed(2) }} }} }} }}
}});

// Prompts per day
new Chart(document.getElementById('sessDay'), {{
  type: 'bar',
  data: {{
    labels: DATES,
    datasets: [{{ label: 'Prompts', data: SESSIONS_BY_DATE,
      backgroundColor: '#22d3ee', borderRadius: 4 }}]
  }},
  options: baseOpts
}});

// Model stacked per day
new Chart(document.getElementById('modelStack'), {{
  type: 'bar',
  data: {{
    labels: DATES,
    datasets: [
      {{ label: 'Opus', data: OPUS_BY_DATE, backgroundColor: '#f59e0b', borderRadius: 2 }},
      {{ label: 'Sonnet', data: SONNET_BY_DATE, backgroundColor: '#6366f1', borderRadius: 2 }}
    ]
  }},
  options: {{ ...baseOpts, scales: {{ ...baseOpts.scales, x: {{ ...baseOpts.scales.x, stacked: true }},
    y: {{ ...baseOpts.scales.y, stacked: true }} }},
    plugins: {{ ...baseOpts.plugins,
      tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.y.toFixed(2) }} }} }} }}
}});

// Session duration per day
new Chart(document.getElementById('durationDay'), {{
  type: 'bar',
  data: {{
    labels: DATES,
    datasets: [{{ label: 'Duration', data: DURATION_BY_DATE,
      backgroundColor: '#f59e0b', borderRadius: 4 }}]
  }},
  options: {{ ...baseOpts,
    scales: {{ ...baseOpts.scales,
      y: {{ ...baseOpts.scales.y,
        ticks: {{ ...baseOpts.scales.y.ticks, callback: v => formatDuration(v) }} }} }},
    plugins: {{ ...baseOpts.plugins,
      tooltip: {{ callbacks: {{ label: ctx => ' ' + formatDuration(ctx.parsed.y) }} }} }} }}
}});

// Avg session duration per day
new Chart(document.getElementById('avgDurationDay'), {{
  type: 'line',
  data: {{
    labels: DATES,
    datasets: [{{ label: 'Avg duration', data: AVG_DURATION_BY_DATE,
      borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,0.15)',
      fill: true, tension: 0.3, pointRadius: 3 }}]
  }},
  options: {{ ...baseOpts,
    scales: {{ ...baseOpts.scales,
      y: {{ ...baseOpts.scales.y,
        ticks: {{ ...baseOpts.scales.y.ticks, callback: v => formatDuration(v) }} }} }},
    plugins: {{ ...baseOpts.plugins,
      tooltip: {{ callbacks: {{ label: ctx => ' ' + formatDuration(ctx.parsed.y) }} }} }} }}
}});

// Cumulative time line
new Chart(document.getElementById('cumulTime'), {{
  type: 'line',
  data: {{
    labels: CUMUL_LABELS,
    datasets: [{{ label: 'Cumulative time', data: CUMUL_DURATION,
      borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.15)',
      fill: true, tension: 0.3, pointRadius: 2 }}]
  }},
  options: {{ ...baseOpts,
    scales: {{ ...baseOpts.scales,
      y: {{ ...baseOpts.scales.y,
        ticks: {{ ...baseOpts.scales.y.ticks, callback: v => formatDuration(v) }} }} }},
    plugins: {{ ...baseOpts.plugins,
      tooltip: {{ callbacks: {{ label: ctx => ' ' + formatDuration(ctx.parsed.y) }} }} }} }}
}});

// Time vs cost scatter
new Chart(document.getElementById('timeVsCost'), {{
  type: 'scatter',
  data: {{
    datasets: [{{ label: 'Prompt', data: SCATTER_DATA,
      backgroundColor: '#34d399', pointRadius: 5, pointHoverRadius: 7 }}]
  }},
  options: {{ ...baseOpts,
    scales: {{ ...baseOpts.scales,
      x: {{ ...baseOpts.scales.x, type: 'linear', min: 0,
        ticks: {{ ...baseOpts.scales.x.ticks, callback: v => formatDuration(v) }},
        title: {{ display: true, text: 'Duration', color: TEXT, font: {{ size: 10 }} }} }},
      y: {{ ...baseOpts.scales.y,
        ticks: {{ ...baseOpts.scales.y.ticks, callback: v => '$' + v.toFixed(2) }},
        title: {{ display: true, text: 'Cost (USD)', color: TEXT, font: {{ size: 10 }} }} }} }},
    plugins: {{ ...baseOpts.plugins,
      tooltip: {{ callbacks: {{
        label: ctx => {{
          const d = ctx.raw;
          return ` ${{d.label}}: ${{formatDuration(d.x)}} / $${{d.y.toFixed(4)}}`;
        }}
      }} }} }} }}
}});

// Tokens per minute scatter
new Chart(document.getElementById('tokensPerMin'), {{
  type: 'scatter',
  data: {{
    datasets: [{{ label: 'Prompt', data: TPM_DATA,
      backgroundColor: '#818cf8', pointRadius: 5, pointHoverRadius: 7 }}]
  }},
  options: {{ ...baseOpts,
    scales: {{ ...baseOpts.scales,
      x: {{ ...baseOpts.scales.x, type: 'linear', min: 0,
        ticks: {{ ...baseOpts.scales.x.ticks, callback: v => formatDuration(v) }},
        title: {{ display: true, text: 'Duration', color: TEXT, font: {{ size: 10 }} }} }},
      y: {{ ...baseOpts.scales.y,
        title: {{ display: true, text: 'Output tokens / min', color: TEXT, font: {{ size: 10 }} }} }} }},
    plugins: {{ ...baseOpts.plugins,
      tooltip: {{ callbacks: {{
        label: ctx => {{
          const d = ctx.raw;
          return ` ${{d.label}}: ${{formatDuration(d.x)}} — ${{d.y}} tok/min`;
        }}
      }} }} }} }}
}});

// Prompt length distribution histogram
new Chart(document.getElementById('durationDist'), {{
  type: 'bar',
  data: {{
    labels: DUR_HIST_LABELS,
    datasets: [{{ label: 'Prompts', data: DUR_HIST_VALUES,
      backgroundColor: '#34d399', borderRadius: 4 }}]
  }},
  options: {{ ...baseOpts,
    plugins: {{ ...baseOpts.plugins, legend: {{ display: false }} }},
    scales: {{ ...baseOpts.scales,
      y: {{ ...baseOpts.scales.y, ticks: {{ ...baseOpts.scales.y.ticks, stepSize: 1 }} }} }} }}
}});

// Total vs key prompts per day
new Chart(document.getElementById('promptsVsTotal'), {{
  type: 'bar',
  data: {{
    labels: ALL_PROMPT_DATES,
    datasets: [
      {{ label: 'Total prompts', data: TOTAL_MSGS_BY_DATE,
         backgroundColor: 'rgba(148,163,184,0.35)', borderRadius: 4 }},
      {{ label: 'Trivial prompts', data: TRIVIAL_BY_DATE,
         backgroundColor: '#34d399', borderRadius: 4 }},
      {{ label: 'Key prompts', data: KEY_PROMPTS_BY_DATE,
         backgroundColor: '#a78bfa', borderRadius: 4 }}
    ]
  }},
  options: baseOpts
}});

// Efficiency % per day
new Chart(document.getElementById('promptEfficiency'), {{
  type: 'line',
  data: {{
    labels: ALL_PROMPT_DATES,
    datasets: [{{ label: 'Efficiency (%)', data: EFFICIENCY_BY_DATE,
      borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.15)',
      fill: true, tension: 0.3, pointRadius: 3, spanGaps: true }}]
  }},
  options: {{ ...baseOpts, plugins: {{ ...baseOpts.plugins,
    tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.parsed.y + '%' }} }} }},
    scales: {{ ...baseOpts.scales,
      y: {{ ...baseOpts.scales.y, min: 0, max: 100,
            ticks: {{ ...baseOpts.scales.y.ticks, callback: v => v + '%' }} }} }} }}
}});

// Category doughnut
new Chart(document.getElementById('promptDonut'), {{
  type: 'doughnut',
  data: {{
    labels: DONUT_LABELS,
    datasets: [{{ data: DONUT_VALUES, backgroundColor: DONUT_COLORS,
      borderWidth: 2, borderColor: '#1e2330' }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: true,
    plugins: {{
      legend: {{ position: 'right', labels: {{ color: TEXT, boxWidth: 12, font: {{ size: 11 }} }} }}
    }}
  }}
}});

// Category stacked per day
new Chart(document.getElementById('promptStack'), {{
  type: 'bar',
  data: {{
    labels: PROMPT_DATES,
    datasets: PROMPT_CAT_DATASETS
  }},
  options: {{ ...baseOpts,
    scales: {{
      x: {{ ...baseOpts.scales.x, stacked: true }},
      y: {{ ...baseOpts.scales.y, stacked: true }}
    }}
  }}
}});
</script>
</body>
</html>
"""

with open(output_file, "w") as f:
    f.write(html)
