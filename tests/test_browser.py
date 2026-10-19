import pytest

from unified_re.adjudication import constraints, make_plan
from unified_re.browser import identify_url, bind_browser_arguments
from unified_re.common import GateError, SKILL, read_json


@pytest.mark.parametrize("url", ["file:///C:/Users/Administrator/.env", "https://user:password@example.com/", "ftp://example.com/", "https://example.com:bad/"])
def test_browser_target_rejects_unreviewed_protocols_and_credentials(url):
    with pytest.raises(GateError):
        identify_url(url)


def test_url_identity_does_not_claim_page_content_hash():
    value = identify_url("https://EXAMPLE.com:443")
    assert value["path"] == "https://example.com/"
    assert "not a page-content hash" in value["identity_kind"]


def test_local_read_permission_does_not_authorize_browser_network():
    with pytest.raises(GateError) as error:
        constraints({"target_type": "web", "permissions": ["read_local"]})
    assert error.value.status == "permission_required"


def browser_plan(context=None):
    catalog = read_json(SKILL / "catalog.json")
    context = {"target_type": "web", "permissions": ["web_read"], **(context or {})}
    retrieved = {"status": "candidates", "candidates": [{"id": s["id"], "capabilities": s["capabilities"], "rank_score": .02} for s in catalog["skills"]]}
    return make_plan(catalog, "Observe CloakBrowser webpage", identify_url("http://127.0.0.1:9001/"), context, retrieved,
                     {"browser_navigate": {"available": True}, "browser_snapshot": {"available": True}})


def test_browser_primary_complement_and_reviewed_tools():
    plan = browser_plan()
    assert plan["phases"][1]["primary_skill"] == "unified:cloakbrowser"
    assert plan["phases"][1]["supplemental_skills"] == ["reverse-skill:browser-automation"]
    assert {t for p in plan["phases"] for t in p["tools"]} == {"cloakbrowser::browser_navigate", "cloakbrowser::browser_snapshot"}


@pytest.mark.parametrize("context", [{"required_provider": "ida"}, {"excluded_providers": ["cloakbrowser"]}, {"required_skill": "reverse-skill:ida-reverse"}])
def test_browser_incompatible_provider_or_skill_cannot_win_by_score(context):
    with pytest.raises(GateError) as error:
        browser_plan(context)
    assert error.value.status in ("unsupported", "policy_conflict")


def test_browser_cannot_navigate_another_target_or_read_extra_output_file():
    task = {"target": identify_url("https://example.com/"), "stage_index": 1, "completed_steps": []}
    with pytest.raises(GateError) as error:
        bind_browser_arguments(task, {"source": "cloakbrowser", "name": "browser_navigate"}, {"url": "https://example.org/"})
    assert error.value.status == "target_mismatch"
    with pytest.raises(GateError):
        bind_browser_arguments(task, {"source": "cloakbrowser", "name": "browser_snapshot"}, {"filename": "C:/outside.md"})


def test_browser_evidence_requires_same_task_navigation():
    task = {"target": identify_url("https://example.com/"), "stage_index": 2, "completed_steps": []}
    with pytest.raises(GateError) as error:
        bind_browser_arguments(task, {"source": "cloakbrowser", "name": "browser_snapshot"}, {})
    assert error.value.status == "needs_context"


def test_browser_snapshot_cannot_read_another_task_artifact(tmp_path):
    from unified_re.browser import snapshot_observation
    path = tmp_path / "page-data.yml"
    path.write_text("must not be read", encoding="utf-8")
    raw = {"content": [{"type": "text", "text": f"### Snapshot\n- [Snapshot]({path})"}]}
    result = snapshot_observation({"id": "owned", "generation": 1}, raw)
    assert result["status"] == "unavailable" and "text" not in result
