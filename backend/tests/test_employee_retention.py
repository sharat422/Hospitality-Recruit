from app.services.employee_retention_service import calculate_retention_risk

def test_low_risk_with_no_signals_is_transparent():
    result=calculate_retention_risk({})
    assert result["risk_score"]==0 and result["risk_level"]=="LOW"
    assert result["model_type"]=="RULES_BASED" and "not a statistical prediction" in result["disclaimer"]

def test_realistic_hospitality_risk_factors_are_explained():
    result=calculate_retention_risk({"attendance":{"absence_days":6,"late_days":8},"salary":{"months_since_increase":26},
      "performance":{"score":88,"promotion_last_18_months":False},"pulse":{"average":2,"decline":1.2},
      "training":{"overdue_count":3},"tenure_months":5})
    assert result["risk_level"] in {"HIGH","CRITICAL"}
    codes={x["code"] for x in result["risk_factors"]}
    assert {"REPEATED_ABSENCE","REPEATED_LATENESS","LOW_PULSE_SCORE","HIGH_PERFORMER_NO_PROGRESSION"} <= codes
    assert all(x["points"]>0 and x["explanation"] for x in result["risk_factors"])

def test_pay_cut_is_a_factor_but_never_a_decision():
    result=calculate_retention_risk({"salary":{"latest_change_pct":-10}})
    assert result["risk_score"]==20 and result["risk_level"]=="LOW"
    assert result["risk_factors"][0]["code"]=="PAY_REDUCTION"
