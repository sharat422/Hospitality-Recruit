from app.services.global_search_service import (
    allowed_categories, complaint_search_allowed, make_result, match_score,
    normalize_query, property_allowed,
)
from app.services.rbac_service import AccessContext


def context(role="RECRUITER", permissions=None, properties=("property-1",)):
    return AccessContext(
        user_id="user-1", org_id="org-1", role=role,
        department_id=None, active_property_id="property-1",
        permissions=frozenset(permissions or {"candidates.read", "jobs.read", "applications.read", "documents.read", "properties.read"}),
        property_ids=frozenset(properties), department_ids=frozenset(),
    )


def test_normalize_and_exact_ranking():
    assert normalize_query("  Ravi   Kumar ") == "ravi kumar"
    assert match_score("Ravi Kumar", ["ravi kumar"]) == (100.0, "exact")


def test_fuzzy_typo_matching():
    score = match_score("houeskeeping", ["Housekeeping Supervisor"])
    assert score is not None
    assert score[1] == "fuzzy"


def test_safe_projection_does_not_include_source_row():
    result = make_result(query="passport", category="documents", row_id="doc-1",
                         title="passport.pdf", subtitle="PASSPORT", url="/pipeline")
    payload = result.as_dict()
    assert set(payload) == {"category", "id", "title", "subtitle", "status", "url", "score", "matchType", "metadata"}
    assert "storage_key" not in payload and "file_url" not in payload


def test_category_permission_filtering():
    allowed = allowed_categories(context(), ["candidates", "employees", "jobs", "complaints"])
    assert allowed == ["candidates", "jobs"]


def test_property_isolation():
    actor = context()
    assert property_allowed(actor, "property-1")
    assert not property_allowed(actor, "property-2")
    assert property_allowed(context(role="OWNER"), "property-2")


def test_posh_never_visible_to_unassigned_owner():
    owner = context(role="OWNER", permissions={"complaints.read"})
    complaint = {"id": "case-1", "complaint_type": "POSH"}
    assert not complaint_search_allowed(owner, complaint, set())
    assert complaint_search_allowed(owner, complaint, {"case-1"})


def test_non_posh_case_requires_assignment_for_manager():
    manager = context(role="HR_MANAGER", permissions={"complaints.read"})
    complaint = {"id": "case-2", "complaint_type": "GENERAL"}
    assert not complaint_search_allowed(manager, complaint, set())
    assert complaint_search_allowed(manager, complaint, {"case-2"})
