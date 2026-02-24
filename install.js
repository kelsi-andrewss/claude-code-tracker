#!/usr/bin/env node
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const scriptDir = path.dirname(path.resolve(__filename));
const bashScript = path.join(scriptDir, 'install.sh');

if (process.platform === 'win32') {
  const result = spawnSync('bash', [bashScript, ...process.argv.slice(2)], {
    stdio: 'inherit',
    shell: false,
  });
  process.exit(result.status || 0);
} else {
  const result = spawnSync('bash', [bashScript, ...process.argv.slice(2)], {
    stdio: 'inherit',
  });
  process.exit(result.status || 0);
}
