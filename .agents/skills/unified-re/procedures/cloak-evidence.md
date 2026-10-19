Capture same-session browser page snapshot as a source-specific observation. 同一 CloakBrowser 会话中记录页面快照、实际 URL 和观察证据。

在本任务导航成功后调用 cloakbrowser::browser_snapshot，保留原始 MCP 结果和实际 Page URL。browser_obs_ 是网关观察引用，不是 REA Evidence。URL 摘要只标识授权地址，不是网页内容哈希。跨源跳转、错误、取消和断线必须显式报告；重连须修订计划。
