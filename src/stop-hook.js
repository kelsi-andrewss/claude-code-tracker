#!/usr/bin/env node
"use strict";

/**
 * Cross-platform stop hook for claude-code-tracker.
 *
 * Called by Claude Code after each session.  On Windows the settings.json
 * hook command is:
 *     node "C:\Users\<user>\.claude\tracking\stop-hook.js"
 *
 * On macOS / Linux the original stop-hook.sh is used instead.
 *
 * Reads JSON from stdin, finds the project's git root, delegates to Python
 * scripts for transcript parsing and chart generation.
 */

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const SCRIPT_DIR = __dirname;

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function findPython() {
  const isWin = process.platform === "win32";
  const candidates = isWin ? ["python", "python3"] : ["python3", "python"];
  for (const cmd of candidates) {
    try {
      execFileSync(cmd, ["--version"], { stdio: "pipe" });
      return cmd;
    } catch {
      // continue
    }
  }
  return isWin ? "python" : "python3";
}

function findGitRoot(startDir) {
  let root = path.resolve(startDir);
  while (true) {
    if (fs.existsSync(path.join(root, ".git"))) return root;
    const parent = path.dirname(root);
    if (parent === root) return null;   // reached filesystem root
    root = parent;
  }
}

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    // Safety: if stdin is already closed, resolve after a short wait
    setTimeout(() => resolve(data), 200);
  });
}

function runPy(script, args, timeout) {
  try {
    execFileSync(PYTHON, [script, ...args], {
      stdio: "pipe",
      timeout: timeout || 30000,
    });
  } catch {
    // Swallow errors — hooks must never break the session
  }
}

// -----------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------

const PYTHON = findPython();

async function main() {
  const raw = await readStdin();
  let input = {};
  try {
    input = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  // --backfill-only mode (SessionStart hook)
  if (process.argv.includes("--backfill-only")) {
    const cwd = input.cwd || "";
    if (!cwd) process.exit(0);
    const projectRoot = findGitRoot(cwd);
    if (!projectRoot) process.exit(0);
    const trackingDir = path.join(projectRoot, ".claude", "tracking");
    if (fs.existsSync(trackingDir)) {
      runPy(path.join(SCRIPT_DIR, "backfill.py"), [projectRoot], 60000);
    }
    process.exit(0);
  }

  // Prevent loops
  if (input.stop_hook_active) process.exit(0);

  const cwd = input.cwd || "";
  const transcript = input.transcript_path || "";
  const sessionId = input.session_id || "";

  if (!cwd || !transcript || !fs.existsSync(transcript)) process.exit(0);

  const projectRoot = findGitRoot(cwd);
  if (!projectRoot) process.exit(0);

  const trackingDir = path.join(projectRoot, ".claude", "tracking");

  // Auto-initialise if the tracking directory doesn't exist yet
  if (!fs.existsSync(trackingDir)) {
    runPy(path.join(SCRIPT_DIR, "init-templates.py"), [trackingDir]);
    runPy(path.join(SCRIPT_DIR, "backfill.py"), [projectRoot], 60000);
  }

  // Parse the transcript and upsert into tokens.json
  const tokensFile = path.join(trackingDir, "tokens.json");
  const projectName = path.basename(projectRoot);

  runPy(
    path.join(SCRIPT_DIR, "parse-session.py"),
    [transcript, tokensFile, sessionId, projectName],
  );

  // Regenerate charts
  runPy(
    path.join(SCRIPT_DIR, "generate-charts.py"),
    [tokensFile, path.join(trackingDir, "charts.html")],
  );

  // Regenerate key-prompts index
  runPy(
    path.join(SCRIPT_DIR, "update-prompts-index.py"),
    [trackingDir],
  );
}

main().catch(() => process.exit(0));
