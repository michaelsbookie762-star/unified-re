import { ensureBinary, browserVersion } from './runtime.mjs';

const executable = await ensureBinary();
console.log(JSON.stringify({ version: browserVersion, executable }, null, 2));
