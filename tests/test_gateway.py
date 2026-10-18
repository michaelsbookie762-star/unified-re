import copy

import pytest

from unified_re.common import GateError, ROOT, SKILL, read_json
from unified_re.engine import Engine
from unified_re.state import Store
from unified_re.targets import identify


@pytest.fixture
def engine(tmp_path):
    return Engine(store=Store(tmp_path / "state.sqlite"))


def task(engine):
    catalog = engine.catalog
    from unified_re.adjudication import make_plan
    target = identify(str(ROOT / "samples/demo-app"))
    retrieved = {"status": "candidates", "candidates": [{"id": s["id"], "rank_score": .02, "capabilities": s["capabilities"]} for s in catalog["skills"]]}
    plan = make_plan(catalog, "inspect scripts", target, {"permissions": ["read_local"]}, retrieved, read_json(ROOT / "reports/discovery.json")["sources"]["rea"]["availability"])
    return engine.store.create({"status": "ready", "plan": plan, "request": "inspect scripts", "target": target, "context": {"permissions": ["read_local"]}})


def test_only_current_stage_loaded(engine):
    data = task(engine)
    loaded = engine.load_stage(data["id"], 1)
    assert loaded["stage"] == "triage"
    assert [t["id"] for t in loaded["tool_definitions"]] == ["rea::binary_session"]
    engine.advance(data["id"], 1)
    loaded = engine.load_stage(data["id"], 1)
    assert loaded["stage"] == "analyze"
    assert len(loaded["tool_definitions"]) == 1
    assert loaded["primary_skill"]["id"] == "unified:rea-javascript"


def test_no_stage_skip_without_successful_analysis(engine):
    data = task(engine)
    engine.advance(data["id"], 1)
    with pytest.raises(GateError) as error:
        engine.advance(data["id"], 1)
    assert error.value.status == "incomplete_stage"


def test_stale_revision_cannot_execute(engine):
    data = task(engine)
    with pytest.raises(GateError) as error:
        engine.load_stage(data["id"], 99)
    assert error.value.status == "stale_plan"


def test_real_original_schema_and_planned_path_enforced(engine):
    data = task(engine)
    tool = engine.tools["rea::analyze_javascript_application"]
    with pytest.raises(GateError) as error:
        engine.bind_arguments(data, tool, {"path": data["target"]["path"]})
    assert error.value.status == "invalid_arguments"
    with pytest.raises(GateError) as error:
        engine.bind_arguments(data, tool, {"input_path": str(ROOT / "samples/second-app")})
    assert error.value.status == "target_mismatch"


def test_cross_task_retained_reference_denied(engine):
    data = task(engine)
    data["evidence"] = [{"evidence_id": "ev_" + "a" * 64, "generation": 1}]
    tool = engine.tools["rea::inspect_analysis_view"]
    with pytest.raises(GateError) as error:
        engine.bind_arguments(data, tool, {"source": {"kind": "retained-evidence", "evidence_id": "ev_" + "b" * 64}, "view": {"kind": "summary"}})
    assert error.value.status == "evidence_mismatch"


def test_raw_specialist_controller_not_injected(engine):
    data = task(engine)
    engine.advance(data["id"], 1)
    loaded = engine.load_stage(data["id"], 1)
    assert "ACTION REQUIRED" not in loaded["primary_skill"]["procedure"]
    with pytest.raises(GateError) as error:
        engine.load_reference(data["id"], 1, "resources/reverse-skill/skills/js-reverse/SKILL.md")
    assert error.value.status == "policy_conflict"


def test_persisted_task_has_no_implicit_live_session(engine, tmp_path):
    data = task(engine)
    other = Engine(store=Store(tmp_path / "state.sqlite"))
    assert other.get(data["id"])["status"] == "disconnected"


def test_selected_specialist_reference_is_loaded_by_page(engine):
    data = task(engine)
    engine.advance(data["id"], 1)
    references = [p for p in read_json(SKILL / "resource-manifest.json") if p["path"].startswith("resources/reverse-skill/skills/js-reverse/") and p["path"].endswith(".md") and not p["path"].endswith("SKILL.md")]
    if not references:
        pytest.skip("Upstream specialist contains no supplementary Markdown reference")
    loaded = engine.load_reference(data["id"], 1, references[0]["path"], limit=120)
    assert len(loaded["text"]) <= 120
    assert loaded["source_sha256"] == references[0]["sha256"]


def test_only_one_discoverable_skill_and_original_layout_preserved():
    assert list((ROOT / ".agents/skills").rglob("SKILL.md")) == [SKILL / "SKILL.md"]
    manifest = read_json(SKILL / "resource-manifest.json")
    from unified_re.common import digest
    assert all(digest((ROOT / record["path"]).read_bytes()) == record["sha256"] for record in manifest)
    assert (ROOT / "resources/reverse-skill/skills/ida-reverse/scripts/start.ps1").is_file()
    assert (ROOT / "resources/reverse-skill/skills/scripts/master-route.ps1").is_file()
    assert (ROOT / "resources/reverse-skill/RULES.md").is_file()


@pytest.mark.asyncio
async def test_wrong_stage_tool_denied_before_backend(engine):
    data = task(engine)
    with pytest.raises(GateError) as error:
        await engine.call(data["id"], 1, "rea::analyze_javascript_application", {"input_path": data["target"]["path"]})
    assert error.value.status == "plan_mismatch"


@pytest.mark.asyncio
async def test_declared_platform_cannot_override_the_live_host(engine):
    import sys
    other = "linux" if sys.platform == "win32" else "windows"
    with pytest.raises(GateError) as error:
        await engine.plan("inspect scripts", str(ROOT / "samples/demo-app"), {"permissions": ["read_local"], "platform": other})
    assert error.value.status == "unsupported"
