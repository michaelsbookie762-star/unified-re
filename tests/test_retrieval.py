import pytest

from unified_re.common import ROOT, SKILL, read_json
from unified_re.retrieval import Index
from scripts.evaluate_retrieval import CASES


@pytest.fixture(scope="module")
def index():
    return Index()


@pytest.mark.parametrize("query,capability", CASES)
def test_real_multilingual_vectors_and_no_match(index, query, capability):
    result = index.search(query, 12)
    assert result["scores_are_confidence"] is False
    if capability is None:
        assert result["status"] == "no_match"
    else:
        assert any(capability in r["capabilities"] for r in result["candidates"])


def test_joint_corpus_contains_both_methods_and_original_tool_contracts(index):
    rows = index.db.execute("SELECT kind,COUNT(*) FROM documents GROUP BY kind").fetchall()
    counts = dict(rows)
    assert counts["skill"] == len(index.catalog["skills"])
    assert counts["tool"] == len(index.catalog["tools"])
    result = index.search("inspect JavaScript application modules", 30)
    assert {r["kind"] for r in result["candidates"]} == {"skill", "tool"}


def test_incremental_update_does_not_reencode_unchanged(index):
    def forbidden(_):
        pytest.fail("Unchanged corpus must not be embedded again")
    original = index.embedder.encode
    index.embedder.encode = forbidden
    try:
        manifest = index.update()
        assert manifest["changed"] == 0
        assert manifest["unchanged"] == len(index.catalog["skills"]) + len(index.catalog["tools"])
    finally:
        index.embedder.encode = original


def test_content_and_version_changes_update_only_affected_records(index, tmp_path):
    catalog = {"version": "owned-test-catalog-1", "skills": [], "tools": []}
    isolated = Index(catalog=catalog, db=tmp_path / "isolated.sqlite", embedder=index.embedder)
    metadata = {"version": "1", "capabilities": ["javascript.static"], "target_types": ["javascript"]}
    rows = [("a", "skill", "fixture", metadata, "Inspect JavaScript module imports"), ("b", "tool", "fixture", metadata, "Read native procedure instructions")]
    isolated.inputs = lambda: iter(rows)
    first = isolated.update()
    before = isolated.db.execute("SELECT vector FROM documents WHERE id='b'").fetchone()[0]
    rows[0] = ("a", "skill", "fixture", {**metadata, "version": "2"}, "Inspect JavaScript module imports and Electron IPC")
    second = isolated.update()
    after = isolated.db.execute("SELECT vector FROM documents WHERE id='b'").fetchone()[0]
    assert first["changed"] == 2
    assert second["changed"] == 1 and second["unchanged"] == 1
    assert before == after
