
# CTF sandbox entry (sidecar, not a second router)


## 为什么单独一层

`CTF-Sandbox-Orchestrator/` 是 **GPL 旁路包**，授权默认是沙箱内部。核心路由包仍是 MIT + `scope.md` 门禁。本 skill 只做关键词入口，不把竞赛树并进核心。


## 任务完成自检（声称完成前 MUST 通过）

- [ ] 我是否先走了 case-init / scope，而不是把“用户说了 CTF”当成已授权外网？
- [ ] 我是否打开了 sidecar orchestrator，而不是把 40 个子技能当 PRIMARY？
- [ ] 若任务其实是 pwn/APK/IDA，我是否让更具体的 PRIMARY 接手？
