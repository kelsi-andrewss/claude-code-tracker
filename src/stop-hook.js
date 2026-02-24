#!/usr/bin/env node
'use strict';
const { execFileSync, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const scriptDir = path.dirname(path.resolve(__filename));
const bashScript = path.join(scriptDir, 'stop-hook.sh');

// On Windows, run via bash (Git Bash / WSL); on Unix, run directly
const input = fs.readFileSync(process.stdin.fd, 'utf8');

if (process.platform === 'win32') {
  const result = spawnSync('bash', [bashScript], {
    input,
    stdio: ['pipe', 'inherit', 'inherit'],
    shell: false,
  });
  process.exit(result.status || 0);
} else {
  const result = spawnSync('bash', [bashScript], {
    input,
    stdio: ['pipe', 'inherit', 'inherit'],
  });
  process.exit(result.status || 0);
}
