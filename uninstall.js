#!/usr/bin/env node
'use strict';
const { spawnSync } = require('child_process');
const path = require('path');

const scriptDir = path.dirname(path.resolve(__filename));
const bashScript = path.join(scriptDir, 'uninstall.sh');

if (process.platform === 'win32') {
  const result = spawnSync('bash', [bashScript], {
    stdio: 'inherit',
    shell: false,
  });
  process.exit(result.status || 0);
} else {
  const result = spawnSync('bash', [bashScript], {
    stdio: 'inherit',
  });
  process.exit(result.status || 0);
}
