#!/usr/bin/env node
"use strict";

/**
 * Cross-platform npm bin wrapper for cost-summary.py.
 *
 * Windows cannot execute .py files via npm bin shebangs, so this thin
 * Node.js wrapper finds the correct Python command and delegates.
 */

const { execFileSync } = require("child_process");
const path = require("path");

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
  console.error("Error: Python not found. Please install Python 3.");
  process.exit(1);
}

const PYTHON = findPython();
const script = path.join(__dirname, "..", "src", "cost-summary.py");

try {
  execFileSync(PYTHON, [script, ...process.argv.slice(2)], {
    stdio: "inherit",
  });
} catch (e) {
  process.exit(e.status || 1);
}
