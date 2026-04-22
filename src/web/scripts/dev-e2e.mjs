#!/usr/bin/env node

import { spawn } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const port = process.env.PLAYWRIGHT_DEV_PORT ?? '3100'
const command = process.platform === 'win32' ? 'npx.cmd' : 'npx'
const env = {
  ...process.env,
  E2E_TEST_MODE: 'playwright',
  NEXT_PUBLIC_E2E_AUTH_BYPASS: 'true',
  NEXT_PUBLIC_STORAGE_DASHBOARD_BETA: process.env.NEXT_PUBLIC_STORAGE_DASHBOARD_BETA ?? 'true',
}
const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDir, '..')

const devProcess = spawn(
  command,
  ['next', 'dev', '--hostname', '127.0.0.1', '--port', port],
  {
    cwd: projectRoot,
    env,
    stdio: 'inherit',
  },
)

devProcess.on('close', (code) => {
  process.exit(code ?? 0)
})
