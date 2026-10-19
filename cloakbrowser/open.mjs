import { launch } from './runtime.mjs';

const url = process.argv[2] || 'about:blank';
const browser = await launch({ headless: false });
try {
  const page = await browser.newPage();
  await page.goto(url);
  console.log(`CloakBrowser ${browser.version()} opened. Close the browser window to exit.`);
  await new Promise(resolve => browser.once('disconnected', resolve));
} finally {
  await browser.close();
}
