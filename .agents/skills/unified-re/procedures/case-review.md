
# Evidence Graph Review

Use this skill when a reverse engineering, forensics, CTF, or authorized security case needs a defensible handoff. It audits the existing `work/<case>/` package without changing the case or touching a target.


## Scope

This skill covers:

- Scope metadata and target-activity readiness
- Evidence record structure and reproducibility fields
- References from work items and timeline entries to Evidence
- Structured Findings and Paths in report Markdown
- Optional SHA-256 verification for case-local artifacts
- A Markdown or JSON review result for a report handoff

It MUST NOT perform reconnaissance, exploitation, dynamic instrumentation, or target changes. Those actions belong to the routed analysis skill and require the case scope gate.


## Tool dependencies

| Tool | Required | Purpose | Auto-bootstrap |
|------|----------|---------|---------------|
| Python 3.9+ | Yes | Runs the read-only case review script | No, use the platform Python installation |

No network access or third-party package is required.


## Workflow

### Phase 1: Intake

Run the review against the existing case directory:

```bash
python3 skills/case-review/scripts/review_case.py work/<case> --format markdown
```

Confirm that `scope.md`, `timeline.md`, `workitems.md`, and `evidence/` are present. A non-strict review reports scope warnings while a strict review treats warnings as handoff blockers.


## Language behavior contract

- Internal reasoning, tool selection, and phase control: English.
- User-visible messages, section labels, reports, and next-step menus: Chinese unless the user requests another language.
- Default bilingual labels place Chinese first and English second, separated by `/`.


## Bootstrap boundary

This skill has no third-party dependency. If Python 3 is unavailable, the only allowed recovery action is the repository bootstrap path when a Python capability is registered for the current platform. If no such capability is registered, stop and report the missing runtime. Do not guess executable paths, download packages, or perform a manual install from inside this skill.


## Routing context

**Upstream entry**: any reverse, forensics, CTF, or authorized security skill that has produced a case package.

**Downstream exit**: `docs-generator/` for a formal report, or the original PRIMARY skill when the graph is incomplete.

**Related modules**: `ops/evidence-finding-path.md`, `ops/timeline-workitem.md`, `digital-forensics/`, `reverse-engineering/`, and `docs-generator/`.


## References

- [NIST SP 800-86: Guide to Integrating Forensic Techniques into Incident Response](https://csrc.nist.gov/pubs/sp/800/86/final)
- [SWGDE Best Practices for Computer Forensic Acquisitions](https://www.swgde.org/documents/published-complete-listing/17-f-002-2-1/)
- [SWGDE Best Practices for Archiving Digital and Multimedia Evidence](https://www.swgde.org/documents/published-complete-listing/19-f-003-best-practices-for-archiving-digital-and-multimedia-evidence/)


## 任务完成自检

- [ ] 我是否审查了 scope.md、timeline.md、workitems.md 和 evidence/？
- [ ] 所有 Finding 是否引用了现存 Evidence？
- [ ] 所有 Path 是否包含合法 path_type 和 Evidence 引用？
- [ ] 是否执行了 hash verification，或记录了未执行原因？
- [ ] 是否以 strict 模式重新运行并保存了 review 结果？
