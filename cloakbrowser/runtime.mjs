import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';

export const root = path.dirname(fileURLToPath(import.meta.url));
export const browserVersion = '146.0.7680.177.5';
// Keep this public-build deployment independent of external binary, license and mirror overrides.
for (const name of ['CLOAKBROWSER_BINARY_PATH', 'CLOAKBROWSER_LICENSE_KEY', 'CLOAKBROWSER_DOWNLOAD_URL', 'CLOAKBROWSER_SKIP_CHECKSUM']) {
  delete process.env[name];
}
process.env.CLOAKBROWSER_CACHE_DIR = path.join(root, 'cache');
process.env.CLOAKBROWSER_VERSION = browserVersion;
process.env.CLOAKBROWSER_AUTO_UPDATE = 'false';
if (existsSync(path.join(root, 'cache', 'license.key'))) {
  throw new Error('Pinned public runtime requires a cache without license.key; the file was not read.');
}

export const { launch, ensureBinary, binaryInfo } = await import('cloakbrowser');
