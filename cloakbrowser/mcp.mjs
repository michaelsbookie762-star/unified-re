// Official Playwright MCP, with the pinned local CloakBrowser launch options.
import { existsSync } from 'node:fs';
import path from 'node:path';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createConnection } from '@playwright/mcp';
import { root, browserVersion, binaryInfo } from './runtime.mjs';
import { buildLaunchOptions } from 'cloakbrowser';

console.log = (...args) => console.error(...args); // stdout is MCP framing only.
if (existsSync(path.join(root, 'cache', 'license.key')))
  throw new Error('Public-build runtime requires a cache without a license.key; the file was not read.');
const info = binaryInfo(browserVersion);
if (!info.installed) throw new Error('missing_dependency: run npm run install:browser explicitly first');
// No download, auto-update, user profile, storage-state or CDP attachment.
const launchOptions = await buildLaunchOptions({headless: true, browserVersion});
const origin = process.env.CLOAK_ALLOWED_ORIGIN;
if (origin && new URL(origin).origin !== origin) throw new Error('Expected one canonical HTTP(S) origin');
const outputDir = process.env.CLOAK_OUTPUT_DIR || path.join(root, 'output', 'mcp', String(process.pid));
if (!path.resolve(outputDir).startsWith(path.join(root, 'output') + path.sep))
  throw new Error('Browser output must stay inside this deployment output directory');
const server = await createConnection({
  browser: {browserName: 'chromium', isolated: true, launchOptions,
    contextOptions: {acceptDownloads: false, serviceWorkers: 'block'}},
  network: origin ? {allowedOrigins: [origin]} : undefined,
  webmcp: false, saveSession: false,
  outputDir, filePaths: 'absolute',
  timeouts: {action: 10000, navigation: 20000, idle: 0},
});
await server.connect(new StdioServerTransport());
process.stdin.once('end', () => { void server.close(); });
