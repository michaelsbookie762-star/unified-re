"""Hard constraints precede specialization, stage, continuity and retrieval."""
from .common import GateError, digest


def equivalence(left, right):
    if left["capabilities"] != right["capabilities"]:
        return {"relationship": "unrelated", "interchangeable": False}
    proven = left.get("behavior_equivalence")
    same = proven and proven == right.get("behavior_equivalence") and left["contract_hash"] == right["contract_hash"] and left["effects"] == right["effects"] and left["target_mode"] == right["target_mode"]
    return {"relationship": "equivalent" if same else "alternative", "interchangeable": bool(same), "reason": "reviewed behavioral proof and complete contracts match" if same else "capability category overlaps; behavior/state equivalence not established"}


def constraints(context):
    allowed = {"permissions", "platform", "read_only", "target_type", "required_skill", "required_provider", "excluded_providers", "capability", "no_commercial", "required_effects", "benign_sample"}
    if set(context) - allowed:
        raise GateError("invalid_arguments", "Unknown context fields are rejected rather than persisted")
    if context.get("platform", "windows") not in ("windows", "linux", "darwin"):
        raise GateError("unsupported", "Host platform is not supported by this registry")
    if context.get("read_only", True) and set(context.get("required_effects", [])) - {"read", "session_write"}:
        raise GateError("policy_conflict", "Required effects contradict read_only constraint")
    if "read_local" not in context.get("permissions", []):
        raise GateError("permission_required", "This local target needs an explicit read_local scope from the user request")
    if context.get("required_provider") in context.get("excluded_providers", []):
        raise GateError("policy_conflict", "The same provider is both required and excluded")
    if context.get("no_commercial") and context.get("required_provider") in ("ida", "hopper", "jeb"):
        raise GateError("policy_conflict", "A commercial provider was required while commercial tools were excluded")
    if set(context.get("required_effects", [])) - {"read", "session_write"}:
        raise GateError("unsupported", "This reviewed gateway does not implement target execution, mutation or active network operations")


def select_primary(skills, target_type, stage, context, ranks, current=None):
    rejected, possible = [], []
    for skill in skills:
        reason = None
        if stage not in skill["stages"]:
            reason = "different_stage"
        elif target_type not in skill["target_types"] and "any" not in skill["target_types"]:
            reason = "target_type_mismatch"
        elif context.get("platform", "windows") not in skill["platforms"]:
            reason = "unsupported_platform"
        elif skill.get("scope") in ("controller", "controller-reference"):
            reason = "second_controller_forbidden"
        required = context.get("required_skill") if stage == "analyze" else None
        if required and skill["id"] != required:
            reason = "user_required_different_skill"
        if reason:
            rejected.append({"id": skill["id"], "reason": reason})
            continue
        specificity = target_type in skill["target_types"]
        score = (int(specificity), skill.get("priority", 0), int(skill["id"] == current), ranks.get(skill["id"], 0))
        possible.append((score, skill))
    if not possible:
        raise GateError("unsupported", "No applicable primary Skill", excluded=rejected)
    possible.sort(key=lambda pair: (pair[0], pair[1]["id"]), reverse=True)
    if len(possible) > 1:
        first, second = possible[0], possible[1]
        if first[0][:3] == second[0][:3] and abs(first[0][3] - second[0][3]) < .001 and first[1]["capabilities"] != second[1]["capabilities"]:
            raise GateError("needs_context", "Equally applicable candidates imply different execution goals", candidates=[first[1]["id"], second[1]["id"]])
    chosen = possible[0][1]
    rejected.extend({"id": skill["id"], "reason": "one_primary_per_stage; lower specialization/stage/continuity/rank"} for _, skill in possible[1:])
    return chosen, rejected


def workflow_order(workflow):
    pending = {p["stage"]: p for p in workflow}
    result = []
    while pending:
        ready = [p for p in pending.values() if set(p["depends_on"]) <= {r["stage"] for r in result}]
        if not ready:
            raise GateError("policy_conflict", "Workflow has cyclic or unresolved stage dependencies", stages=list(pending))
        for phase in ready:
            result.append(phase)
            pending.pop(phase["stage"])
    return result


def make_plan(catalog, request, target, context, retrieved, availability, providers=None):
    constraints(context)
    if retrieved["status"] == "no_match":
        raise GateError("no_match", "No relevant capability; no nearest-result fallback")
    target_type = target["type"]
    selected_id = catalog["default_operations"].get(target_type)
    if context.get("capability"):
        options = [t for t in catalog["tools"] if t["reviewed"] and t["stage"] == "analyze" and context["capability"] in t["capabilities"] and target_type in t["target_types"]]
        if len(options) != 1:
            raise GateError("needs_context" if options else "unsupported", "Explicit capability needs one reviewed matching operation", candidates=[t["id"] for t in options])
        selected_id = options[0]["id"]
    if not selected_id:
        raise GateError("unsupported", "Target type has no reviewed executable adapter", target_type=target_type)
    operation = selected_id.split("::", 1)[1]
    # Relevance must actually support the intended capability, not merely match
    # an unrelated result elsewhere in a large catalog.
    relevant_caps = {cap for row in retrieved["candidates"] for cap in row["capabilities"]}
    expected_cap = next((t["capabilities"][0] for t in catalog["tools"] if t["id"] == "rea::" + operation), None)
    if expected_cap not in relevant_caps:
        raise GateError("no_match", "Retrieved capabilities do not support this target and requested analysis")
    if context.get("required_provider") and target_type != "native":
        raise GateError("policy_conflict", "A deep-analysis provider cannot be forced onto a target-free operation")
    tools = {t["id"]: t for t in catalog["tools"]}
    if selected_id not in tools or not tools[selected_id]["reviewed"]:
        raise GateError("unsupported", "Tool contract has not been reviewed", tool=selected_id)
    fact = availability.get(operation)
    if fact is None:
        raise GateError("needs_context", "Tool missing from live availability inventory", tool=selected_id)
    # A target-free operation cannot use a declared catalog entry as readiness.
    prerequisite_open = tools[selected_id]["target_mode"] == "active" and fact.get("reason") == "target_required" and is_available(availability.get("open_binary", {}))
    if not is_available(fact) and not prerequisite_open:
        raise GateError(classify_unavailable(fact), "REA operation is not currently available", tool=selected_id, availability=fact)
    native_provider = None
    if target_type == "native" and tools[selected_id]["target_mode"] == "active":
        # Native ownership and concrete provider identity need explicit evidence.
        # No attached GUI or mutable shared database is silently adopted.
        candidates = providers or []
        required = context.get("required_provider")
        candidates = [p for p in candidates if not required or p["provider"]["id"] == required]
        available = [p for p in candidates if p.get("availability", {}).get("status") == "available" and p["provider"]["id"] not in context.get("excluded_providers", []) and not (context.get("no_commercial") and p["provider"]["id"] in ("ida", "hopper", "jeb"))]
        reasons = [{"provider": p["provider"], "availability": p.get("availability"), "target_support": p.get("target_support")} for p in candidates]
        state = "needs_context" if available or providers is None else "missing_dependency"
        if required and candidates and candidates[0].get("availability", {}).get("code") == "unsupported_host":
            state = "unsupported"
        if len(available) != 1:
            raise GateError(state, "Native deep analysis needs one available provider; no silent selection or fallback", tool=selected_id, availability=fact, provider_candidates=reasons)
        native_provider = available[0]["provider"]["id"]
        if native_provider != "ghidra":
            raise GateError("needs_context", "The configured native route has no reviewed owned-instance binding; attached GUI databases cannot be adopted", provider=native_provider)
        if context.get("platform", "windows") == "windows" and context.get("benign_sample") is not True:
            raise GateError("needs_context", "Windows Ghidra P0 needs an explicitly classified benign local sample")
        if context.get("required_skill") in ("reverse-skill:ida-reverse", "reverse-skill:radare2"):
            raise GateError("policy_conflict", "Required primary Skill does not match the available concrete Ghidra route")
    ranks = {r["id"]: r["rank_score"] for r in retrieved["candidates"]}
    phases, excluded = [], []
    for definition in workflow_order(catalog["workflow"]):
        stage = definition["stage"]
        primary, rejected = select_primary(catalog["skills"], target_type, stage, context, ranks)
        excluded.extend(rejected)
        supplements = []
        if stage == "analyze" and target_type in ("javascript", "electron"):
            supplements = ["reverse-skill:js-reverse"]
        if stage == "analyze" and native_provider == "ghidra":
            supplements = ["reverse-skill:ghidra-reverse"]
        if stage == "synthesis":
            supplements = ["reverse-skill:docs-generator", "reverse-skill:case-review"]
        selected = {"triage": ["rea::binary_session"], "analyze": [selected_id], "evidence": ["rea::inspect_analysis_view", "rea::get_evidence_bundle"], "synthesis": []}[stage]
        if stage == "analyze" and tools[selected_id]["target_mode"] == "active":
            selected.insert(0, "rea::open_binary")
            if native_provider:
                selected.insert(1, "rea::list_procedures")
        supplements = [s for s in supplements if s != primary["id"]]
        phases.append({"stage": stage, "primary_skill": primary["id"], "supplemental_skills": supplements, "tools": selected, "required_calls": [selected_id] if stage == "analyze" else [], "dependencies": [{"source": "rea", "package": "rea-agents@6.5.0", "live_availability_required": True}], "stage_dependencies": definition["depends_on"], "input": definition["input"], "output": definition["output"]})
    selected_ids = {t for phase in phases for t in phase["tools"]}
    excluded_tools = [{"id": t["id"], "reason": "unreviewed_parameters_effects_or_target_binding" if not t["reviewed"] else "different_capability_or_stage"} for t in catalog["tools"] if t["id"] not in selected_ids and (t["name"] == operation or t["capabilities"] == tools[selected_id]["capabilities"])]
    plan = {"status": "ready", "request": request, "target": target, "context": context, "catalog_version": catalog["version"], "selected_provider": native_provider, "provider_instance_kind": "REA-owned-ephemeral-database" if native_provider == "ghidra" else None, "current_stage": "triage", "phases": phases, "execution_order": [f"{p['stage']}:{t}" for p in phases for t in p["tools"]], "excluded_candidates": excluded + excluded_tools, "relations": [r for r in catalog["relations"] if any(s["id"] in str(r) for s in catalog["skills"] if s["id"] in [p["primary_skill"] for p in phases] + [v for p in phases for v in p["supplemental_skills"]])], "alternatives": [{"source": "direct MCP / other REA provider", "trigger": "selected backend fails or becomes unavailable", "action": "stop; retain evidence; explicit revised plan and verified target/instance binding required", "automatic_switch": False}], "unresolved": []}
    plan["retrieval_provenance"] = {"model_fingerprint": retrieved.get("model_fingerprint"), "index_representation": retrieved.get("index_representation"), "candidate_ranks": [{key: row.get(key) for key in ("id", "semantic_rank", "bm25_rank", "rank_score")} for row in retrieved["candidates"]], "scores_are_confidence": False}
    plan["plan_hash"] = digest(plan)
    return plan


def is_available(fact):
    # Exact upstream values are preserved; unknown variants fail closed.
    return fact.get("available") is True or fact.get("availability") == "available" or fact.get("status") == "available"


def classify_unavailable(fact):
    raw = str(fact).lower()
    if any(word in raw for word in ("missing", "not installed", "dependency", "not configured", "not_configured")):
        return "missing_dependency"
    if any(word in raw for word in ("unsupported", "not supported", "host_unsupported")):
        return "unsupported"
    if any(word in raw for word in ("unhealthy", "timeout", "temporar", "failed")):
        return "backend_failure"
    return "needs_context"
