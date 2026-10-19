import { createServer } from 'node:http';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { test, expect } from '@playwright/test';
import { launch, root, browserVersion } from '../runtime.mjs';

test('CloakBrowser starts, navigates and interacts at desktop and mobile sizes', async () => {
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>CloakBrowser 本地验证</title>
    <style>body{font-family:system-ui;margin:24px}main{max-width:600px}input,button{padding:12px;max-width:100%;box-sizing:border-box}input{width:100%}button{margin-top:16px}</style>
    <main><h1>CloakBrowser 本地验证</h1><label>名称 <input aria-label="名称"></label>
    <button onclick="document.querySelector('output').textContent='已验证：'+document.querySelector('input').value">验证</button>
    <p><output aria-live="polite"></output></p></main></html>`;
  const server = createServer((_request, response) => {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end(html);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await launch({ headless: true });
    expect(browser.version()).toBe(browserVersion.split('.').slice(0, 4).join('.'));
    const errors = [];
    await mkdir(path.join(root, 'output', 'playwright'), { recursive: true });
    for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => {
        if (message.type() === 'error') errors.push(message.text());
      });
      await page.goto(`http://127.0.0.1:${server.address().port}/`);
      await expect(page).toHaveTitle('CloakBrowser 本地验证');
      await page.getByRole('textbox', { name: '名称' }).fill('测试用户');
      await page.getByRole('button', { name: '验证', exact: true }).click();
      await expect(page.locator('output')).toHaveText('已验证：测试用户');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: path.join(root, 'output', 'playwright', `${viewport.width}.png`), fullPage: true });
      await context.close();
    }
    expect(errors).toEqual([]);
    console.log(JSON.stringify({ browser: browser.version(), navigation: 'passed', interaction: 'passed', consoleErrors: errors.length }));
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
});
