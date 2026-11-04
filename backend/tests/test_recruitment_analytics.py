from app.services.recruitment_analytics_service import aggregate


def test_all_recruitment_metrics_use_persisted_rows():
    applications = [
        {"id": "a1", "candidate_id": "c1", "job_id": "j1", "source": "REFERRAL", "status": "HIRED", "created_at": "2026-01-01T00:00:00Z", "hired_at": "2026-01-11T00:00:00Z"},
        {"id": "a2", "candidate_id": "c2", "job_id": "j1", "source": "NAUKRI", "status": "HIRED", "created_at": "2026-01-02T00:00:00Z", "hired_at": "2026-01-22T00:00:00Z"},
        {"id": "a3", "candidate_id": "c3", "job_id": "j2", "source": "NAUKRI", "status": "OFFER", "created_at": "2026-01-03T00:00:00Z"},
        {"id": "a4", "candidate_id": "c4", "job_id": "j2", "source": "DIRECT", "status": "INTERVIEW", "created_at": "2026-01-04T00:00:00Z"},
        {"id": "a5", "candidate_id": "c5", "job_id": "j2", "source": "DIRECT", "status": "SHORTLISTED", "created_at": "2026-01-05T00:00:00Z"},
    ]
    result = aggregate(
        applications=applications,
        jobs=[{"id": "j1", "status": "open", "openings_count": 2, "created_at": "2026-01-01T00:00:00Z"}],
        costs=[{"amount_inr": 6000}, {"amount_inr": 4000}],
        ghosting=[{"risk_level": "HIGH"}, {"risk_level": "LOW"}],
        referrals=[{"status": "HIRED"}, {"status": "APPLIED"}],
        candidate_users={"c1": "e1", "c2": "e2"},
        performance=[{"employee_id": "e1", "overall_score": 80}, {"employee_id": "e2", "rating": 4}],
    )
    assert result["applications"] == 5
    assert result["hires"] == 2
    assert result["time_to_hire_days"] == 15
    assert result["time_to_fill_days"] == 21
    assert result["interview_conversion_pct"] == 75
    assert result["offer_acceptance_pct"] == 66.7
    assert result["cost"] == {"total_inr": 10000.0, "cost_per_hire_inr": 5000.0, "entries": 2}
    assert result["ghosting"]["rate_pct"] == 50
    assert result["referrals"]["conversion_pct"] == 50
    assert result["quality_of_hire"]["average_score"] == 80
    assert next(x for x in result["source_performance"] if x["source"] == "NAUKRI")["conversion_pct"] == 50


def test_incomplete_samples_are_unavailable_not_invented():
    result = aggregate(applications=[{"id": "a1", "status": "SUBMITTED", "source": None}], jobs=[])
    assert result["time_to_hire_days"] is None
    assert result["time_to_fill_days"] is None
    assert result["cost"]["cost_per_hire_inr"] is None
    assert result["quality_of_hire"]["average_score"] is None
    assert result["funnel"][0]["count"] == 1


def test_funnel_is_cumulative():
    result = aggregate(applications=[{"status": "APPLIED"}, {"status": "SHORTLISTED"}, {"status": "HIRED"}], jobs=[])
    counts = {row["stage"]: row["count"] for row in result["funnel"]}
    assert counts == {"APPLIED": 3, "SCREENED": 2, "SHORTLISTED": 2, "INTERVIEW": 1, "SELECTED": 1, "OFFER": 1, "OFFER_ACCEPTED": 1, "ONBOARDING": 1, "HIRED": 1}
