from app.services.training_career_service import calculate_promotion_readiness, score_quiz


def test_quiz_scoring_is_deterministic():
    questions=[{"id":"q1","correct_option":"A"},{"id":"q2","correct_option":"B"}]
    assert score_quiz(questions,{"q1":"A","q2":"C"}) == {"score":50.0,"correct":1,"total":2}


def test_readiness_requires_all_inputs():
    step={"required_skills":[{"skill_id":"guest","min_proficiency":3}],"required_course_ids":["course-1"],
          "minimum_performance_score":80,"minimum_tenure_months":0}
    result=calculate_promotion_readiness(step=step,employee_skills=[{"skill_id":"guest","proficiency":3}],
        completed_course_ids={"course-1"},performance_score=85)
    assert result["ready"] is True
    assert result["readiness_score"] >= 95


def test_readiness_explains_gaps_and_never_promotes():
    step={"required_skills":[{"skill_id":"upsell","min_proficiency":4}],"required_course_ids":["course-2"],
          "minimum_performance_score":75,"minimum_tenure_months":12}
    result=calculate_promotion_readiness(step=step,employee_skills=[],completed_course_ids=set(),performance_score=60)
    assert result["ready"] is False
    assert result["missing_skills"][0]["skill_id"] == "upsell"
    assert result["missing_course_ids"] == ["course-2"]
    assert "manager action" in result["advisory"]
