"""Reviewed URL identity and observation plan for an owned CloakBrowser process."""
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .common import GateError, ROOT, digest


def identify_url(value, expected_type=None):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise GateError("invalid_arguments", "Invalid HTTP(S) target URL")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
        raise GateError("policy_conflict", "Expected an explicit HTTP(S) URL without embedded credentials")
    if expected_type and expected_type != "web":
        raise GateError("needs_context", "URL conflicts with the declared local target type")
    hostname = parsed.hostname.lower()
    hostname = f"[{hostname}]" if ":" in hostname else hostname
    authority = hostname + (f":{port}" if port and (parsed.scheme, port) not in (("http", 80), ("https", 443)) else "")
    origin = parsed.scheme + "://" + authority
    url = urlunsplit((parsed.scheme, authority, parsed.path or "/", parsed.query, parsed.fragment))
    return {"path": url, "type": "web", "origin": origin, "sha256": digest(url.encode()), "files": [], "bytes": None,
            "identity_kind": "authorized-url-digest; not a page-content hash"}


def observed_url(raw):
    text = "\n".join(c.get("text", "") for c in raw.get("content", []) if c.get("type") == "text")
    found = re.search(r"(?m)^- Page URL: (.+)$", text)
    return found.group(1).strip() if found else None


def snapshot_observation(task, raw):
    """Read only this generation's MCP-generated snapshot; keep raw reply intact."""
    text = "\n".join(c.get("text", "") for c in raw.get("content", []) if c.get("type") == "text")
    link = re.search(r"(?m)^### Snapshot\r?\n- \[Snapshot\]\(([^)]+)\)", text)
    if not link:
        inline = re.search(r"### Snapshot\r?\n```yaml\r?\n(.*?)\r?\n```", text, re.S)
        if inline:
            content = inline.group(1)
            return {"status": "observed", "kind": "browser-accessibility-snapshot", "source": "inline MCP snapshot",
                    "sha256": digest(content.encode()), "text": content[:60000], "truncated": len(content) > 60000,
                    "authority": "untrusted page observation; distinct from REA Evidence"}
        return None
    path = Path(link.group(1))
    allowed = ROOT / "cloakbrowser/output/tasks" / f"{task['id']}-g{task['generation']}"
    try:
        resolved = path.resolve()
        linked_parent = any(p.is_symlink() or p.is_junction() for p in path.parents if p.is_relative_to(ROOT))
        if not path.is_absolute() or path.is_symlink() or linked_parent or not resolved.is_relative_to(ROOT) or not resolved.is_relative_to(allowed.resolve()) or path.suffix != ".yml" or not path.name.startswith("page-"):
            return {"status": "unavailable", "reason": "snapshot artifact is outside this task's output scope"}
        if path.stat().st_size > 4 * 1024 * 1024:
            return {"status": "unavailable", "reason": "snapshot exceeds bounded 4 MiB read; request a narrower snapshot"}
        data = path.read_bytes()
        content = data.decode("utf-8")
        return {"status": "observed", "kind": "browser-accessibility-snapshot", "path": str(resolved.relative_to(ROOT)),
                "sha256": digest(data), "text": content[:60000], "truncated": len(content) > 60000,
                "authority": "untrusted page observation; distinct from REA Evidence"}
    except (OSError, UnicodeError):
        return {"status": "unavailable", "reason": "owned snapshot artifact could not be read"}


def make_browser_plan(catalog, request, target, context, retrieved, availability):
    from .adjudication import select_primary, workflow_order
    if context.get("required_provider") not in (None, "cloakbrowser") or "cloakbrowser" in context.get("excluded_providers", []):
        raise GateError("policy_conflict", "CloakBrowser URL route conflicts with the requested/excluded provider")
    if context.get("capability") not in (None, "web.observe"):
        raise GateError("unsupported", "Reviewed browser gateway currently supports web.observe only")
    if "web.observe" not in {cap for c in retrieved["candidates"] for cap in c["capabilities"]}:
        raise GateError("no_match", "Retrieved capabilities do not support browser observation")
    tools = {"triage": ["cloakbrowser::browser_snapshot"], "analyze": ["cloakbrowser::browser_navigate"],
             "evidence": ["cloakbrowser::browser_snapshot"], "synthesis": []}
    for name in ("browser_navigate", "browser_snapshot"):
        if not availability.get(name, {}).get("available"):
            raise GateError("missing_dependency", "Owned browser MCP did not expose the reviewed operation", tool=name)
    phases, rejected = [], []
    ranks = {c["id"]: c["rank_score"] for c in retrieved["candidates"]}
    for definition in workflow_order(catalog["workflow"]):
        stage = definition["stage"]
        primary, excluded = select_primary(catalog["skills"], "web", stage, context, ranks)
        rejected.extend(excluded)
        phases.append({**definition, "primary_skill": primary["id"],
                       "supplemental_skills": ["reverse-skill:browser-automation"] if stage == "analyze" else [],
                       "tools": tools[stage], "required_calls": tools[stage] if stage in ("analyze", "evidence") else [],
                       "dependencies": [{"source": "cloakbrowser", "browser": "146.0.7680.177.5", "mcp": "@playwright/mcp@0.0.83", "live_availability_required": True}]})
    plan = {"status": "ready", "request": request, "target": target, "context": context, "catalog_version": catalog["version"],
            "selected_provider": "cloakbrowser", "provider_instance_kind": "task-owned isolated browser; no user profile",
            "current_stage": "triage", "phases": phases, "execution_order": [f"{p['stage']}:{t}" for p in phases for t in p["tools"]],
            "excluded_candidates": rejected + [{"id": t["id"], "reason": "different_backend_or_unreviewed_browser_effect"} for t in catalog["tools"] if t["id"] not in {v for names in tools.values() for v in names}],
            "relations": [r for r in catalog["relations"] if "cloak" in str(r)],
            "alternatives": [{"source": "another browser/REA static analysis", "trigger": "selected backend fails or task needs a different effect", "action": "stop; explicitly revise target and plan", "automatic_switch": False}],
            "unresolved": [], "limitations": ["Page JavaScript executes during navigation; this is not static REA analysis.", "URL identity is not immutable page-content identity.", "Only planned navigation and snapshots are reviewed; input, upload and evaluation tools are not executable through this gateway."]}
    plan["retrieval_provenance"] = {"model_fingerprint": retrieved.get("model_fingerprint"), "candidate_ranks": [{k: c.get(k) for k in ("id", "semantic_rank", "bm25_rank", "rank_score")} for c in retrieved["candidates"]], "scores_are_confidence": False}
    plan["plan_hash"] = digest(plan)
    return plan


def bind_browser_arguments(task, tool, arguments):
    if tool["source"] != "cloakbrowser":
        raise GateError("plan_mismatch", "Browser task cannot borrow another backend session")
    if tool["name"] == "browser_navigate" and identify_url(arguments.get("url", ""))["path"] != task["target"]["path"]:
        raise GateError("target_mismatch", "Navigation URL differs from the planned target")
    if arguments.get("filename"):
        raise GateError("policy_conflict", "Caller-chosen output paths are outside this observation plan")
    if tool["name"] == "browser_snapshot" and task["stage_index"] > 0 and "cloakbrowser::browser_navigate" not in task["completed_steps"]:
        raise GateError("needs_context", "Evidence snapshot requires this task's successful navigation")
