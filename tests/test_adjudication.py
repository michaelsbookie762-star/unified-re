import copy

import pytest

from unified_re.adjudication import classify_unavailable, constraints, equivalence, make_plan, select_primary, workflow_order
from unified_re.common import GateError, ROOT, SKILL, read_json
from unified_re.state import Store
from unified_re.targets import identify


@pytest.fixture
def catalog():
    return read_json(SKILL / "catalog.json")


def context(**changes):
    return {"permissions": ["read_local"], "platform": "windows", **changes}


def candidates(catalog):
    return {"status": "candidates", "candidates": [{"id": s["id"], "capabilities": s["capabilities"], "rank_score": .02} for s in catalog["skills"]]}


def test_complementary_stages_and_one_primary(catalog):
    availability = read_json(ROOT / "reports/discovery.json")["sources"]["rea"]["availability"]
    plan = make_plan(catalog, "inspect JavaScript application", identify(str(ROOT / "samples/demo-app")), context(), candidates(catalog), availability)
    assert [p["stage"] for p in plan["phases"]] == ["triage", "analyze", "evidence", "synthesis"]
    assert all(isinstance(p["primary_skill"], str) for p in plan["phases"])
    assert plan["phases"][1]["primary_skill"] == "unified:rea-javascript"
    assert plan["phases"][1]["supplemental_skills"] == ["reverse-skill:js-reverse"]
    assert not plan["alternatives"][0]["automatic_switch"]


def test_equivalent_category_does_not_mean_interchangeable(catalog):
    left = next(t for t in catalog["tools"] if t["id"] == "rea::list_strings")
    right = next(t for t in catalog["tools"] if t["id"] == "ghidra::list_strings")
    left, right = copy.deepcopy(left), copy.deepcopy(right)
    left["capabilities"] = right["capabilities"] = ["native.strings"]
    assert equivalence(left, right) == {"relationship": "alternative", "interchangeable": False, "reason": "capability category overlaps; behavior/state equivalence not established"}
    right["contract_hash"] = left["contract_hash"]
    assert equivalence(left, right)["interchangeable"] is False
    left["behavior_equivalence"] = right["behavior_equivalence"] = "verified-read-contract-v1"
    right["target_mode"] = left["target_mode"]
    right["effects"] = left["effects"]
    assert equivalence(left, right)["interchangeable"] is True


def test_same_name_keeps_source_and_schema(catalog):
    tools = [t for t in catalog["tools"] if t["name"] == "list_strings"]
    assert {t["id"] for t in tools} >= {"rea::list_strings", "ghidra::list_strings"}
    assert len({t["contract_hash"] for t in tools}) > 1
    assert len(catalog["tools"]) == len({t["id"] for t in catalog["tools"]})


def test_mutually_exclusive_primaries_and_hard_preference(catalog):
    selected, rejected = select_primary(catalog["skills"], "native", "analyze", context(required_skill="reverse-skill:ghidra-reverse"), {})
    assert selected["id"] == "reverse-skill:ghidra-reverse"
    assert any(r["id"] == "reverse-skill:ida-reverse" for r in rejected)


def test_semantic_score_never_overrides_platform(catalog):
    skills = copy.deepcopy(catalog["skills"])
    for skill in skills:
        if skill["id"] == "unified:rea-javascript":
            skill["platforms"] = ["linux"]
    selected, rejected = select_primary(skills, "javascript", "analyze", context(), {"unified:rea-javascript": 10000})
    assert selected["id"] == "reverse-skill:js-reverse"
    assert {"id": "unified:rea-javascript", "reason": "unsupported_platform"} in rejected


@pytest.mark.parametrize("change,status", [({"required_effects": ["execute_target"]}, "policy_conflict"), ({"permissions": []}, "permission_required"), ({"required_provider": "ida", "excluded_providers": ["ida"]}, "policy_conflict")])
def test_contradictions_fail_closed(change, status):
    with pytest.raises(GateError) as error:
        constraints(context(**change))
    assert error.value.status == status


def test_close_candidates_with_material_goal_difference_need_context():
    common = {"stages": ["analyze"], "target_types": ["native"], "platforms": ["windows"], "priority": 1, "scope": "specialist"}
    skills = [{**common, "id": "a", "capabilities": ["native.metadata"]}, {**common, "id": "b", "capabilities": ["native.analyze"]}]
    with pytest.raises(GateError) as error:
        select_primary(skills, "native", "analyze", context(), {"a": .029, "b": .0295})
    assert error.value.status == "needs_context"


@pytest.mark.parametrize("fact,expected", [({"available": False, "reason": "missing dependency"}, "missing_dependency"), ({"available": False, "reason": "unsupported host"}, "unsupported"), ({"available": False, "reason": "temporary timeout"}, "backend_failure"), ({"available": False, "reason": "target_required"}, "needs_context")])
def test_backend_failure_classes(fact, expected):
    assert classify_unavailable(fact) == expected


def test_catalog_listing_does_not_prove_live_availability(catalog):
    with pytest.raises(GateError) as error:
        make_plan(catalog, "inspect scripts", identify(str(ROOT / "samples/demo-app")), context(), candidates(catalog), {"analyze_javascript_application": {"available": False, "reason": "missing dependency"}})
    assert error.value.status == "missing_dependency"


def test_no_match_is_not_nearest_fallback(catalog):
    with pytest.raises(GateError) as error:
        make_plan(catalog, "write a cake recipe", identify(str(ROOT / "samples/demo-app")), context(), {"status": "no_match"}, {})
    assert error.value.status == "no_match"


def test_backend_aliases_share_atomic_exclusive_lease(tmp_path):
    first = Store(tmp_path / "state.sqlite")
    second = Store(tmp_path / "state.sqlite")
    # The REA-IDA alias and direct IDA route point to the same instance key.
    first.acquire("rea-task", ["ida-http://127.0.0.1:13337"])
    with pytest.raises(GateError) as error:
        second.acquire("direct-task", ["another-free-key", "ida-http://127.0.0.1:13337"])
    assert error.value.status == "resource_busy"
    assert len(first.leases()) == 1  # partial lease acquisition rolls back
    second.release("rea-task")  # a foreign process may not release it
    assert len(first.leases()) == 1
    first.release("rea-task")
    second.acquire("direct-task", ["ida-http://127.0.0.1:13337"])


@pytest.mark.parametrize("resource", ["browser:tab:42", "database:connection:main", "device:serial:owned-fixture"])
def test_other_shared_state_has_the_same_ownership_gate(tmp_path, resource):
    store = Store(tmp_path / "state.sqlite")
    store.acquire("task-a", [resource])
    with pytest.raises(GateError) as error:
        store.acquire("task-b", [resource])
    assert error.value.status == "resource_busy"


def test_secret_files_excluded_before_read(tmp_path):
    secret = tmp_path / ".env"
    secret.write_text("a harmless test placeholder", encoding="utf-8")
    with pytest.raises(GateError) as error:
        identify(str(tmp_path))
    assert error.value.status == "policy_conflict"


def test_safe_type_identification_reports_conflict():
    with pytest.raises(GateError) as error:
        identify(str(ROOT / "samples/demo-app"), "native")
    assert error.value.status == "needs_context"


def test_cyclic_or_missing_dependency_is_an_explicit_conflict():
    for definitions in ([{"stage": "a", "depends_on": ["b"]}, {"stage": "b", "depends_on": ["a"]}], [{"stage": "a", "depends_on": ["missing"]}]):
        with pytest.raises(GateError) as error:
            workflow_order(definitions)
        assert error.value.status == "policy_conflict"


def test_complement_order_comes_from_shared_catalog_not_list_order(catalog):
    stages = workflow_order(list(reversed(catalog["workflow"])))
    assert [p["stage"] for p in stages] == ["triage", "analyze", "evidence", "synthesis"]


def test_available_owned_ghidra_has_explicit_provider_and_open_order(catalog):
    availability = read_json(ROOT / "reports/discovery.json")["sources"]["rea"]["availability"]
    providers = [{"provider": {"id": "ghidra", "version": "fixture-version"}, "availability": {"status": "available"}}]
    # A policy fixture establishes planning semantics, not real Ghidra execution.
    plan = make_plan(catalog, "decompile native procedure", {"type": "native"}, context(benign_sample=True), candidates(catalog), availability, providers)
    assert plan["selected_provider"] == "ghidra"
    assert plan["provider_instance_kind"] == "REA-owned-ephemeral-database"
    assert plan["phases"][1]["tools"] == ["rea::open_binary", "rea::list_procedures", "rea::analyze_function"]


def test_native_missing_dependency_is_based_on_real_provider_inventory(catalog):
    rea = read_json(ROOT / "reports/discovery.json")["sources"]["rea"]
    providers = rea["session"]["structuredContent"]["result"]["analysis_provider_candidates"]
    if any(p["availability"]["status"] == "available" for p in providers):
        pytest.skip("This environment now has an available native provider")
    with pytest.raises(GateError) as error:
        make_plan(catalog, "decompile native procedure", {"type": "native"}, context(), candidates(catalog), rea["availability"], providers)
    assert error.value.status == "missing_dependency"
    assert error.value.details["provider_candidates"]
