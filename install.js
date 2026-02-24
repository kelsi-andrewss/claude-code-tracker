#!/usr/bin/env node
"use strict";

/**
 * Cross-platform installer for claude-code-tracker.
 *
 * Replaces `bash ./install.sh` as the npm postinstall hook so that
 * installation works on Windows, macOS, and Linux.
 *
 * On macOS Homebrew installs the script detects the Cellar path and
 * delegates to the original install.sh (bash is always available there).
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync, execFileSync } = require("child_process");

const SCRIPT_DIR = __dirname;
const HOME = os.homedir();
const INSTALL_DIR = path.join(HOME, ".claude", "tracking");
const SETTINGS = path.join(HOME, ".claude", "settings.json");
const IS_WIN = process.platform === "win32";

// -----------------------------------------------------------------------
// Homebrew detection — delegate to original install.sh
// -----------------------------------------------------------------------
if (SCRIPT_DIR.includes(path.sep + "Cellar" + path.sep)) {
  console.log("Homebrew install detected — deferring to install.sh");
  try {
    execSync(`bash "${path.join(SCRIPT_DIR, "install.sh")}"`, {
      stdio: "inherit",
    });
  } catch {
    process.exit(1);
  }
  process.exit(0);
}

console.log("Installing claude-code-tracker...");

// -----------------------------------------------------------------------
// Find Python
// -----------------------------------------------------------------------
function findPython() {
  const candidates = IS_WIN
    ? ["python", "python3"]
    : ["python3", "python"];
  for (const cmd of candidates) {
    try {
      execFileSync(cmd, ["--version"], { stdio: "pipe" });
      return cmd;
    } catch {
      // continue
    }
  }
  console.error(
    "Error: Python not found. Please install Python 3.\n" +
      "  https://www.python.org/downloads/"
  );
  process.exit(1);
}
const PYTHON = findPython();

// -----------------------------------------------------------------------
// Copy scripts to ~/.claude/tracking/
// -----------------------------------------------------------------------
fs.mkdirSync(INSTALL_DIR, { recursive: true });

// Remove old scripts (clean reinstall)
if (fs.existsSync(INSTALL_DIR)) {
  for (const f of fs.readdirSync(INSTALL_DIR)) {
    if (f.endsWith(".sh") || f.endsWith(".py") || f.endsWith(".js")) {
      fs.unlinkSync(path.join(INSTALL_DIR, f));
    }
  }
}

// Copy src/ scripts
const srcDir = path.join(SCRIPT_DIR, "src");
for (const f of fs.readdirSync(srcDir)) {
  if (f.endsWith(".sh") || f.endsWith(".py") || f.endsWith(".js")) {
    fs.copyFileSync(path.join(srcDir, f), path.join(INSTALL_DIR, f));
  }
}

// On Unix, make scripts executable
if (!IS_WIN) {
  for (const f of fs.readdirSync(INSTALL_DIR)) {
    if (f.endsWith(".sh") || f.endsWith(".py")) {
      fs.chmodSync(path.join(INSTALL_DIR, f), 0o755);
    }
  }
}

// Determine the hook command — Node on Windows, bash script on Unix
const hookCmd = IS_WIN
  ? `node "${path.join(INSTALL_DIR, "stop-hook.js")}"`
  : path.join(INSTALL_DIR, "stop-hook.sh");

console.log(`Scripts installed to ${INSTALL_DIR}`);

// -----------------------------------------------------------------------
// Install skills to ~/.claude/skills/
// -----------------------------------------------------------------------
const skillsSrc = path.join(SCRIPT_DIR, "skills");
if (fs.existsSync(skillsSrc)) {
  for (const skillName of fs.readdirSync(skillsSrc)) {
    const skillDir = path.join(skillsSrc, skillName);
    if (!fs.statSync(skillDir).isDirectory()) continue;
    const skillMd = path.join(skillDir, "SKILL.md");
    if (!fs.existsSync(skillMd)) continue;
    const dest = path.join(HOME, ".claude", "skills", skillName);
    fs.mkdirSync(dest, { recursive: true });
    fs.copyFileSync(skillMd, path.join(dest, "SKILL.md"));
    console.log(`Skill installed: ${skillName}`);
  }
}

// -----------------------------------------------------------------------
// Patch settings.json — register hooks
// -----------------------------------------------------------------------
let settings = {};
if (fs.existsSync(SETTINGS)) {
  try {
    settings = JSON.parse(fs.readFileSync(SETTINGS, "utf8"));
  } catch {
    settings = {};
  }
}

const hookEntry = {
  type: "command",
  command: hookCmd,
  timeout: 30,
  async: true,
};

if (!settings.hooks) settings.hooks = {};

// --- Stop hook ---
if (!settings.hooks.Stop) settings.hooks.Stop = [];
// Remove any existing stop-hook entries (from npm or brew)
settings.hooks.Stop = settings.hooks.Stop.filter(
  (g) =>
    !g.hooks ||
    !g.hooks.some(
      (h) => h.command && (h.command.includes("stop-hook.sh") || h.command.includes("stop-hook.js"))
    )
);
settings.hooks.Stop.push({ hooks: [hookEntry] });

// --- SessionStart hook (backfill) ---
const backfillCmd = hookCmd + " --backfill-only";
if (!settings.hooks.SessionStart) settings.hooks.SessionStart = [];
settings.hooks.SessionStart = settings.hooks.SessionStart.filter(
  (g) =>
    !g.hooks ||
    !g.hooks.some(
      (h) => h.command && (h.command.includes("stop-hook.sh") || h.command.includes("stop-hook.js"))
    )
);
settings.hooks.SessionStart.push({
  hooks: [
    { type: "command", command: backfillCmd, timeout: 60, async: true },
  ],
});

// --- permissions.allow ---
if (!settings.permissions) settings.permissions = {};
if (!settings.permissions.allow) settings.permissions.allow = [];
settings.permissions.allow = settings.permissions.allow.filter(
  (e) => !e.includes("stop-hook")
);
if (IS_WIN) {
  settings.permissions.allow.push(
    `Bash(node "${path.join(INSTALL_DIR, "stop-hook.js")}"*)`
  );
} else {
  settings.permissions.allow.push(
    `Bash(${path.join(INSTALL_DIR, "stop-hook.sh")}*)`
  );
}

fs.mkdirSync(path.dirname(SETTINGS), { recursive: true });
fs.writeFileSync(SETTINGS, JSON.stringify(settings, null, 2) + "\n");
console.log("Hook registered in " + SETTINGS);

// -----------------------------------------------------------------------
// Patch ~/.claude/CLAUDE.md — add tracking instruction
// -----------------------------------------------------------------------
const claudeMd = path.join(HOME, ".claude", "CLAUDE.md");
const marker = "planning session ends without implementation";
let claudeContent = "";
if (fs.existsSync(claudeMd)) {
  claudeContent = fs.readFileSync(claudeMd, "utf8");
}

if (!claudeContent.includes(marker)) {
  const addition =
    "\n- When a planning session ends without implementation (plan rejected, " +
    "approach changed, or pure research), still write a tracking entry \u2014 " +
    "mark it as architecture category and note what was decided against and why.\n";
  fs.appendFileSync(claudeMd, addition);
  console.log("Tracking instruction added to " + claudeMd);
} else {
  console.log("CLAUDE.md tracking instruction already present.");
}

// -----------------------------------------------------------------------
// Backfill historical sessions for the current project
// -----------------------------------------------------------------------
function findGitRoot(startDir) {
  let root = path.resolve(startDir);
  while (true) {
    if (fs.existsSync(path.join(root, ".git"))) return root;
    const parent = path.dirname(root);
    if (parent === root) return null;
    root = parent;
  }
}

const projectRoot = findGitRoot(process.cwd());
if (projectRoot) {
  console.log("Backfilling historical sessions...");
  try {
    execFileSync(PYTHON, [path.join(INSTALL_DIR, "backfill.py"), projectRoot], {
      stdio: "inherit",
      timeout: 60000,
    });
  } catch {
    // Non-fatal — backfill can fail if no transcripts exist yet
  }
}

// -----------------------------------------------------------------------
// Check project .gitignore — warn if .claude/ is not covered
// -----------------------------------------------------------------------
function checkGitignore(projectRoot) {
  if (!projectRoot) return;
  const gitignorePath = path.join(projectRoot, ".gitignore");
  let covered = false;
  if (fs.existsSync(gitignorePath)) {
    const lines = fs.readFileSync(gitignorePath, "utf8").split(/\r?\n/);
    covered = lines.some((l) => {
      const trimmed = l.trim();
      return (
        trimmed === ".claude" ||
        trimmed === ".claude/" ||
        trimmed === "**/.claude" ||
        trimmed === "**/.claude/"
      );
    });
  }
  if (!covered) {
    console.log(
      "\n" +
      "╔══════════════════════════════════════════════════════════════╗\n" +
      "║  ⚠  WARNING: .claude/ is NOT in your .gitignore             ║\n" +
      "║                                                              ║\n" +
      "║  Your tracking data (costs, tokens, key prompts) will be    ║\n" +
      "║  committed to git and pushed to GitHub.                     ║\n" +
      "║                                                              ║\n" +
      "║  Add this line to your project's .gitignore:               ║\n" +
      "║                                                              ║\n" +
      "║      .claude/                                               ║\n" +
      "║                                                              ║\n" +
      "╚══════════════════════════════════════════════════════════════╝"
    );
  }
}

checkGitignore(projectRoot);

console.log(
  "\nclaude-code-tracker installed successfully.\n" +
    "Restart Claude Code to activate tracking."
);
