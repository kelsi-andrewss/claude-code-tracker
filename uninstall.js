#!/usr/bin/env node
"use strict";

/**
 * Cross-platform uninstaller for claude-code-tracker.
 *
 * Removes installed scripts from ~/.claude/tracking/, unregisters hooks
 * from settings.json, and removes installed skills.
 *
 * On macOS Homebrew installs, delegates to the original uninstall.sh.
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync } = require("child_process");

const SCRIPT_DIR = __dirname;
const HOME = os.homedir();
const INSTALL_DIR = path.join(HOME, ".claude", "tracking");
const SETTINGS = path.join(HOME, ".claude", "settings.json");

// -----------------------------------------------------------------------
// Homebrew detection
// -----------------------------------------------------------------------
if (SCRIPT_DIR.includes(path.sep + "Cellar" + path.sep)) {
  console.log("Homebrew install detected — deferring to uninstall.sh");
  try {
    execSync(`bash "${path.join(SCRIPT_DIR, "uninstall.sh")}"`, {
      stdio: "inherit",
    });
  } catch {
    // continue
  }
  process.exit(0);
}

console.log("Uninstalling claude-code-tracker...");

// -----------------------------------------------------------------------
// Remove scripts from ~/.claude/tracking/
// -----------------------------------------------------------------------
if (fs.existsSync(INSTALL_DIR)) {
  for (const f of fs.readdirSync(INSTALL_DIR)) {
    if (f.endsWith(".sh") || f.endsWith(".py") || f.endsWith(".js")) {
      fs.unlinkSync(path.join(INSTALL_DIR, f));
    }
  }
  console.log(`Scripts removed from ${INSTALL_DIR}`);
} else {
  console.log(`Nothing to remove at ${INSTALL_DIR}`);
}

// -----------------------------------------------------------------------
// Remove installed skills
// -----------------------------------------------------------------------
const skillsSrc = path.join(SCRIPT_DIR, "skills");
if (fs.existsSync(skillsSrc)) {
  for (const skillName of fs.readdirSync(skillsSrc)) {
    const dest = path.join(HOME, ".claude", "skills", skillName);
    if (fs.existsSync(dest)) {
      fs.rmSync(dest, { recursive: true, force: true });
      console.log(`Skill removed: ${skillName}`);
    }
  }
}

// -----------------------------------------------------------------------
// Remove hooks from settings.json
// -----------------------------------------------------------------------
if (fs.existsSync(SETTINGS)) {
  try {
    const data = JSON.parse(fs.readFileSync(SETTINGS, "utf8"));
    let removed = false;

    function hasStopHook(g) {
      return (
        g.hooks &&
        g.hooks.some(
          (h) =>
            h.command &&
            (h.command.includes("stop-hook.sh") || h.command.includes("stop-hook.js"))
        )
      );
    }

    // Stop hook
    if (data.hooks && data.hooks.Stop) {
      const before = data.hooks.Stop.length;
      data.hooks.Stop = data.hooks.Stop.filter((g) => !hasStopHook(g));
      if (data.hooks.Stop.length < before) removed = true;
      if (data.hooks.Stop.length === 0) delete data.hooks.Stop;
    }

    // SessionStart hook
    if (data.hooks && data.hooks.SessionStart) {
      data.hooks.SessionStart = data.hooks.SessionStart.filter(
        (g) => !hasStopHook(g)
      );
      if (data.hooks.SessionStart.length === 0)
        delete data.hooks.SessionStart;
    }

    // Clean up empty hooks object
    if (data.hooks && Object.keys(data.hooks).length === 0) {
      delete data.hooks;
    }

    // permissions.allow
    if (data.permissions && data.permissions.allow) {
      data.permissions.allow = data.permissions.allow.filter(
        (e) => !e.includes("stop-hook")
      );
      if (data.permissions.allow.length === 0) delete data.permissions.allow;
      if (
        data.permissions &&
        Object.keys(data.permissions).length === 0
      ) {
        delete data.permissions;
      }
    }

    fs.writeFileSync(SETTINGS, JSON.stringify(data, null, 2) + "\n");
    console.log(
      removed
        ? "Hook removed from " + SETTINGS
        : "Hook not found in " + SETTINGS
    );
  } catch {
    // Non-fatal
  }
}

console.log("\nclaude-code-tracker uninstalled.");
