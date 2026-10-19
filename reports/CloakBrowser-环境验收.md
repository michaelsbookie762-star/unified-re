# CloakBrowser 部署与环境验收

观察时间：2026-10-20T00:25:32+08:00，Asia/Shanghai。结论：**核心运行环境与浏览器已就绪；全部专项分析环境尚未配齐。**

## 已完成部署

- unified：本项目 `cloakbrowser/`；reverse：`~/.codex/reverse-skill/cloakbrowser/`。两处各有固定 npm 依赖和固定浏览器缓存，不依赖彼此的目录链接。
- 固定 cloakbrowser 0.5.12、公开 Chromium 146.0.7680.177.5、官方 Playwright MCP 0.0.83；Playwright UI 测试使用 1.64.0。
- 官方签名清单重新通过 Ed25519 校验，压缩包 SHA-256 为 `b213795cb32c3169f766c74ce1d0275fc89d3df256de39c04da7fb4c23b7fdbe`；两处 chrome.exe、chrome.dll 均与该压缩包内对应文件一致。版本及文件摘要在 `cloakbrowser/SOURCES.lock.json`。
- 复用已有官方下载包，仅复制白名单运行文件和指定版本的浏览器构建；未复制账号、浏览器资料或登录状态。没有安装新商业分析器。
- reverse 的 Git 检出及实际 Codex 活动副本 `~/.cc-switch/skills/reverse-skill` 同步增加 CloakBrowser 浏览器分支、专项引用和 R19 触发词。Pi 显式读取的检出路径与 Codex 活动副本均覆盖。
- unified 保留一个主 SKILL.md。目录为 54 项方法、318 个工具定义，其中 17 个 REA 操作及 3 个浏览器操作完成契约审查（浏览器关闭仅用于内部清理）。上游 424 份原始资源及版本不被本地扩展改写。
- 当前目录版本：`937bbaba80fa629cd5d3017c2e2b703cb0a09e0a039ccea8585688b0e6108bce`。工具只按 `source::tool` 标识；浏览器会话不与 JSHook、日常 Chrome 或 REA 共用。

## 使用方法

重启 Codex、重新启动 Pi，让已有全局 unified-re 入口加载更新。在聊天中输入：

```text
请用 unified-re 的 CloakBrowser 观察这个我已授权访问的网页：https://example.com/
先 task_plan，再按阶段导航、读取页面快照并给出观察报告。
```

`task_plan.target_path` 支持明确 HTTP(S) URL，`context.permissions` 需 `web_read`，只声明用户已有授权。本地样本仍使用 `read_local`。网页会执行页面 JavaScript，不能把它称作不运行目标的静态分析。

当前网关只执行计划内导航和快照，并负责关闭自己创建的临时浏览器。官方 MCP 另有点击、填表等工具定义，但检索命中不赋予网关执行权限；本地交互脚本应在用户授权范围内使用 Playwright API。`browser_obs_` 是浏览器观察引用，独立于 REA Evidence。URL 摘要不是页面内容哈希；快照内容另有哈希。内联快照直接保留，文件快照仅从本任务/代次输出目录读取，拒绝链接路径和跨任务文件，限制 4 MiB 读取并显式标记文本截断。

手动窗口：双击任一部署目录中的 `start.cmd`。单独 MCP 客户端使用 `node <该目录绝对路径>/mcp.mjs`；服务不会自动把工具加入既有聊天，也不会在启动时下载新浏览器。

## 本机运行环境

- Python **3.13.15**、Node **24.14.1** 已实际运行。Git、uv、npm/npx、PowerShell 和 Java 入口存在。
- 本项目 Python 依赖完整性/版本、ONNX 模型摘要和索引已在启动及测试中核对；`uv pip check` 检查 59 个已装包，无依赖冲突。
- 两处 `npm ls --depth=0` 均确认固定的 wrapper、MCP、SDK 和 Playwright 版本。模型、索引、浏览器的成功调用为实际执行证据，而非仅配置存在。
- Java 为 REA 实际探测到的 64 位 JDK 21.0.12.1；未配置 Ghidra 安装目录前，不能据此确认满足具体 Ghidra 版本的要求。

## MCP 与分析引擎现场检查

| 后端 | 当前协议观察 | 工具数 | 实际能力/依赖状态 |
|---|---|---:|---|
| rea | 通过 | 207 | JS/归档真实验收通过；原生提供方未配齐 |
| idapro | 失败 | 0 | 初始化失败，13337 不可达；Python 桥存在不等于 IDA 可用 |
| ghidra | 通过 | 27 | 工具发现成功，但 8080 不可达；REA GHIDRA_INSTALL_DIR 未配置 |
| jshook | 通过 | 8 | 仅初始化/工具发现通过；未附着用户浏览器或测试实际分析 |
| reqable-mcp | 通过 | 46 | 工具发现成功，但 9000 不可达；Reqable 实际调用未验 |
| pentestswarm | 通过，但有协议异常（1 条） | 5 | 可返回工具列表，但协议有异常；未执行安全测试任务 |
| cloakbrowser | 通过 | 25 | 两处真实浏览器/MCP 验证通过 |

Burp 桥会读取令牌文件，Anything Analyzer 依赖凭据，Xquik 依赖 OAuth；本次均未启动，不读取其秘密或账户状态，状态为**未验证**。其他已登记 MCP 的存在也不代表全部功能已验收；本次对上表项目进行协议层核查。

REA 的原生候选：Ghidra 为 `not_configured`（GHIDRA_INSTALL_DIR 未设置），IDA 为 `not_configured`（REA_IDA_MCP_CONFIG 未设置），Hopper 为 Windows `unsupported_host`。本次不宣称原生反编译端到端可用，也没有为完成测试安装商业工具。

## 专项环境缺项

现场检查覆盖旧工具索引中列出的入口及常用补充入口，共 59 项 PATH 查询。以下是 **PATH 未找到** 的清单，MCP 专用入口或项目局部包以对应协议/包检查为准，不能把这里的 no 直接解释为全盘未安装：

```text
CloakBrowser, adb, agent-browser, analyzeHeadless, anything-analyzer, apksigner, apktool, binaryninja, binwalk, bkcrack, burpsuite-mcp, codeql, dnSpy, docker, dotnet, frida, frida-ps, ghidra, ghidra-mcp, ida, idapro, jadx, jeb-pro, jshookmcp, kubectl, nmap, pentestswarm, proxycat, pwntools, r2, r2mcp, r2pm, r2xsql, r2xsql-full, rabin2, radiff2, radius2, rahash2, rasm2, rax2, reqable-mcp, seclists, semgrep, xquik-mcp, yara, zipalign
```

需要继续配置的典型专项包括 Android（JADX/APKTool/ADB/签名工具）、Frida 动态分析、radare2、.NET/dnSpy、固件工具、部分漏洞扫描与代码审计工具。Ghidra/Reqable 需要实际应用或后端运行，IDA 需要核对安装、桥入口与服务配置。设备、驱动、商业许可、目标程序及第三方服务授权未进行真实任务验收；WSL/容器和未登记自定义安装目录没有穷尽扫描。

旧 `skills/tool-index.md` 的扫描时间较早，不能代替本次现场结果。完整机器可读记录保存在本机 `reports/environment-audit.json`，reverse 同时保存于 `cloakbrowser/output/environment-audit.json`。没有修改其它 MCP 全局条目，也未执行全量 bootstrap。

## 验证结果

- Python 测试：**64 项通过，0 失败/错误**。
- unified → 官方 MCP → 真实 CloakBrowser：**25 项检查通过**，包含中英文召回、权限隔离、单主/互补 Skill、URL 绑定、未审查工具拒绝、页面内容与哈希、来源区分、报告、目标切换、错误、取消、断线、显式重连、最终租约/会话清空。
- reverse 独立 MCP：**5 项检查通过**，真实初始化、25 个工具发现、本地导航、同会话快照内容、关闭。
- 两处 Playwright 浏览器 UI 测试均通过：中文输入、按钮点击、1280×800 与 390×844、无横向溢出、页面脚本错误为 0。截图在各自 `cloakbrowser/output/playwright/`。
- 原有真实 REA 7 项及统一网关 24 项回归通过；Codex、Pi 两份全局配置的真实初始化/检索调用通过。
- reverse：175/175 路由用例通过、路由一致性通过、smoke 通过；CloakBrowser 命中 R19。三个 Skill 入口结构校验通过。

断线检查修复了退出取消中断清理的问题：先关闭本任务拥有的临时浏览器，再结束传输，清理屏蔽外层取消信号。失败测试产生的自有本地夹具租约曾进行限定范围核对，任务和原始记录保留；没有清理用户资源。对真正无法核对所有权的外部共享租约，仍返回 needs_context，不自动夺取。

原始调用、错误和测试产物留在本机 `reports/`、`var/` 与浏览器 `output/`，不随 Git 推送。此报告中的检查数量是本次验收条目数，不是成功率或性能指标。

## 限制与来源

仅完成本机 Windows 实测，没有在第二台空白机器验证完整下载重装。没有检测站、验证码、第三方防护绕过或代理出口结论；没有读取用户浏览器登录状态、.env、密钥或验证码。独立临时会话、URL 检查及 MCP origin guard 不是操作系统安全沙箱。

官方依据：[CloakBrowser](https://github.com/CloakHQ/CloakBrowser)、[Playwright MCP](https://github.com/microsoft/playwright-mcp)、[浏览器二进制条款](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md)。wrapper/MCP 许可证已保留；浏览器二进制、依赖与模型不打包提交。
