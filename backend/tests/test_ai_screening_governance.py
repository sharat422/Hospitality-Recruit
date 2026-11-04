from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services import candidate_screening_service as service


WAITER_JOB = {
    "title": "Senior Waiter",
    "department": "F&B",
    "required_skills": ["table service", "pos systems", "guest relations"],
    "experience_min_years": 2,
    "required_languages": ["Hindi", "English"],
    "location_city": "Mumbai",
    "salary_min_inr": 18000,
    "salary_max_inr": 24000,
    "urgency_days": 30,
    "shift_requirements": ["evening", "weekends"],
}


def candidate(**overrides):
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "first_name": "Rajesh",
        "last_name": "Kumar",
        "email": "rajesh@example.com",
        "phone": "+919876543210",
        "city": "Mumbai",
        "parsed_skills": ["table service", "POS systems", "guest relations", "upselling"],
        "years_experience": 4,
        "hospitality_experience_years": 3,
        "languages": ["Hindi", "English", "Marathi"],
        "expected_salary_inr": 22000,
        "notice_period_days": 15,
        "availability": ["evening", "weekends"],
        "work_history": [{"title": "Waiter", "industry": "hotel", "duration_months": 36}],
    }
    row.update(overrides)
    return row


def test_realistic_waiter_scores_high_with_reasons():
    result = service.deterministic_score_candidate(candidate(), WAITER_JOB)
    assert result["total_score"] >= 80
    assert result["overall_recommendation"] == "shortlist"
    assert len(result["recommendation_reasons"]) >= 3
    assert result["scoring_weights"] == service.DEFAULT_WEIGHTS


def test_salary_and_shift_mismatch_are_visible():
    result = service.deterministic_score_candidate(
        candidate(expected_salary_inr=40000, availability=["morning"]), WAITER_JOB,
    )
    assert result["salary_score"] == 30
    assert result["availability_score"] == 35
    assert "does not match" in result["availability_explanation"]


@pytest.mark.asyncio
async def test_bpo_transfer_applies_only_to_matching_front_desk_role():
    bpo = candidate(parsed_skills=["customer support"], years_experience=2,
                    hospitality_experience_years=0,
                    work_history=[{"title": "BPO Associate", "industry": "call center", "duration_months": 24}])
    front_desk = {**WAITER_JOB, "title": "Front Desk Executive", "department": "Front Office"}
    chef = {**WAITER_JOB, "title": "Commis Chef", "department": "Kitchen"}
    matching = await service.score_candidate(bpo, front_desk, use_ai_explanation=False)
    non_matching = await service.score_candidate(bpo, chef, use_ai_explanation=False)
    assert matching.cross_industry_match is True
    assert matching.cross_industry_source == "call_center"
    assert non_matching.cross_industry_match is False


def test_configurable_weights_change_total_reproducibly():
    row = candidate(expected_salary_inr=40000)
    baseline = service.deterministic_score_candidate(row, WAITER_JOB)
    salary_heavy = {"skill": .10, "experience": .10, "language": .10, "location": .10, "salary": .50, "availability": .10}
    changed = service.deterministic_score_candidate(row, WAITER_JOB, salary_heavy)
    assert changed["total_score"] < baseline["total_score"]
    assert changed["scoring_weights"]["salary"] == .50


def test_invalid_weights_are_rejected():
    with pytest.raises(ValueError, match="sum to 1.0"):
        service.validate_weights({"skill": .9})


def test_blind_mode_removes_identity_and_location():
    blinded = service.apply_blind_mode(candidate(photo_url="photo", hometown="Jaipur", gender="male"))
    for key in ("first_name", "last_name", "email", "phone", "photo_url", "city", "hometown", "gender"):
        assert key not in blinded
    assert blinded["work_history"][0].get("company") is None


@pytest.mark.asyncio
async def test_ai_explanation_cannot_change_deterministic_score(monkeypatch):
    baseline = await service.score_candidate(candidate(), WAITER_JOB, use_ai_explanation=False)
    malicious_explanation = AsyncMock(return_value={
        "skill_score": 0,
        "total_score": 0,
        "overall_recommendation": "reject",
        "skill_explanation": "AI-provided explanation only.",
        "summary": "Recruiter review is required.",
    })
    monkeypatch.setattr(service, "_claude_explain_deterministic", malicious_explanation)
    explained = await service.score_candidate(candidate(), WAITER_JOB, use_ai_explanation=True)
    assert explained.total_score == baseline.total_score
    assert explained.skill.score == baseline.skill.score
    assert explained.overall_recommendation == baseline.overall_recommendation
    assert explained.skill.explanation == "AI-provided explanation only."


def test_shortlist_never_mutates_without_recruiter_confirmation():
    result = service.auto_shortlist(None, "job-id", None, "org-id", top_n=10)
    assert result["requires_confirmation"] is True
    assert result["shortlisted"] == 0

