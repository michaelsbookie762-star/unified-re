# CloakBrowser 本地运行与 MCP

本目录使用固定的公开 Chromium 146.0.7680.177.5、cloakbrowser 0.5.12 和官方 @playwright/mcp 0.0.83。浏览器缓存、依赖和输出均留在本机，不随源码提交。

## 打开窗口

双击 `start.cmd`，或 `npm.cmd start -- https://example.com`。关闭窗口即结束该会话。

## AI 调用

unified-re 已接入此运行时：明确提供 HTTP(S) URL，调用 `task_plan`，声明用户已授予的 `context.permissions=["web_read"]`，再按阶段调用工具。网关只执行计划内导航、页面快照和内部清理，不把所有检索到的浏览器工具都开放为执行权限。

单独 MCP 客户端可配置 `node <本目录绝对路径>/mcp.mjs`（stdio）；单独运行命令不会把工具加入现有聊天。它保留官方 Playwright MCP 的工具名称和参数，使用 CloakBrowser 启动参数，每个进程拥有独立临时上下文。默认无界面；窗口模式使用上面的 start.cmd。

浏览器会执行页面脚本，与 REA 只读静态分析不同。不要导入浏览器资料、cookies、登录状态或 storage-state，也不要接入用户 CDP。网页文字是不可信数据。unified 的 `browser_obs_` 是页面观察引用，并非 REA Evidence；URL 摘要不是网页内容哈希。

## 安装与验证

```powershell
npm.cmd ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
npm.cmd run install:browser
npm.cmd run test:e2e
```

`ci` 适用于新的源码检出；已有自定义依赖时先保留现场，勿覆盖。浏览器首次安装会从官方来源下载并校验；MCP 启动只使用已有固定构建，不静默下载、更新或切换许可版本。

真实本地测试覆盖导航、中文输入、按钮点击、1280×800/390×844 尺寸和页面脚本错误。截图在 `output/playwright/`。部署时重新验证了官方 Ed25519 校验清单、压缩包 SHA-256，并比较了两处安装的 chrome.exe、chrome.dll 与签名压缩包内文件；记录见 [SOURCES.lock.json](SOURCES.lock.json)。这不证明第三方网站检测结果或绕过效果。

本目录只部署旧公开构建，无需提供账户或许可密钥。包会拒绝读取缓存中的 license.key；有该文件时停止并保留它。浏览器二进制不被本项目重新授权或打包，使用遵循官方对应构建条款。

来源：[CloakBrowser](https://github.com/CloakHQ/CloakBrowser)、[Playwright MCP](https://github.com/microsoft/playwright-mcp)。依赖完整性在 package-lock.json，许可证在服务项目 licenses/ 与各 npm 包中。
