"""Transparent employee attrition risk rules; not a statistical prediction."""
from __future__ import annotations
from datetime import date, datetime

MODEL_TYPE = "RULES_BASED"
MODEL_VERSION = "RETENTION_RULES_V1"

def _days_since(value):
    if not value: return None
    parsed = date.fromisoformat(str(value)[:10])
    return max(0, (date.today()-parsed).days)

def calculate_retention_risk(data: dict) -> dict:
    """Return an explainable 0-100 risk score from auditable operational signals."""
    factors=[]; actions=[]; score=0
    attendance=data.get("attendance") or {}
    absences=int(attendance.get("absence_days") or 0); late=int(attendance.get("late_days") or 0)
    if absences >= 5:
        points=min(25,10+(absences-5)*3); score+=points
        factors.append({"code":"REPEATED_ABSENCE","points":points,"value":absences,"window_days":90,"explanation":f"{absences} validated absence days in 90 days"})
        actions.append({"code":"WELLBEING_CHECKIN","label":"Schedule a private wellbeing and attendance check-in"})
    elif absences >= 3:
        score+=8; factors.append({"code":"RISING_ABSENCE","points":8,"value":absences,"window_days":90,"explanation":f"{absences} validated absence days in 90 days"})
    if late >= 6:
        points=min(15,6+(late-6)*2); score+=points
        factors.append({"code":"REPEATED_LATENESS","points":points,"value":late,"window_days":90,"explanation":f"Late arrival recorded on {late} validated days"})
        actions.append({"code":"SHIFT_FIT_REVIEW","label":"Review commute, roster and shift preference"})
    salary=data.get("salary") or {}; change=float(salary.get("latest_change_pct") or 0); stagnant=int(salary.get("months_since_increase") or 0)
    if change < 0:
        score+=20; factors.append({"code":"PAY_REDUCTION","points":20,"value":change,"explanation":f"Latest monthly gross change was {change:.1f}%"})
        actions.append({"code":"COMPENSATION_REVIEW","label":"Review compensation change with HR"})
    elif stagnant >= 24:
        score+=12; factors.append({"code":"PAY_STAGNATION","points":12,"value":stagnant,"explanation":f"No recorded increase for {stagnant} months"})
        actions.append({"code":"MARKET_PAY_REVIEW","label":"Run a role and market compensation review"})
    performance=data.get("performance") or {}; perf=performance.get("score")
    if perf is not None and float(perf) >= 80 and not performance.get("promotion_last_18_months"):
        score+=12; factors.append({"code":"HIGH_PERFORMER_NO_PROGRESSION","points":12,"value":perf,"explanation":"High performance without a recorded promotion in 18 months"})
        actions.append({"code":"CAREER_CONVERSATION","label":"Agree a documented career pathway and promotion criteria"})
    pulse=data.get("pulse") or {}; avg=pulse.get("average")
    if avg is not None and float(avg) <= 2.5:
        points=20 if float(avg)<=2 else 15; score+=points
        factors.append({"code":"LOW_PULSE_SCORE","points":points,"value":avg,"explanation":f"Recent pulse average is {float(avg):.1f}/5"})
        actions.append({"code":"ENGAGEMENT_CHECKIN","label":"Hold a confidential engagement check-in"})
    if pulse.get("decline") is not None and float(pulse["decline"]) >= 1:
        score+=10; factors.append({"code":"PULSE_DECLINE","points":10,"value":pulse["decline"],"explanation":f"Pulse score declined by {float(pulse['decline']):.1f} points"})
    training=data.get("training") or {}; overdue=int(training.get("overdue_count") or 0)
    if overdue >= 2:
        score+=8; factors.append({"code":"TRAINING_DISENGAGEMENT","points":8,"value":overdue,"explanation":f"{overdue} assigned courses are overdue"})
        actions.append({"code":"LEARNING_PLAN_REVIEW","label":"Review workload and learning plan"})
    tenure=int(data.get("tenure_months") or 0)
    if 2 <= tenure <= 6:
        score+=6; factors.append({"code":"EARLY_TENURE_WINDOW","points":6,"value":tenure,"explanation":f"Employee is in the first {tenure} months of employment"})
        actions.append({"code":"EARLY_TENURE_CHECKIN","label":"Run a 30/60/90-day retention check-in"})
    prior=data.get("turnover") or {}; prior_events=prior.get("prior_events") or []
    if any(str(event).upper() in {"RESIGNED","ABSCONDED"} for event in prior_events):
        score+=5; factors.append({"code":"PRIOR_EMPLOYMENT_EXIT","points":5,"value":prior_events,"explanation":"A prior exit is recorded for this rehired employee"})
        actions.append({"code":"REHIRE_EXPECTATIONS_CHECKIN","label":"Confirm role expectations and reasons for returning"})
    score=round(min(100,score),2)
    level="CRITICAL" if score>=70 else "HIGH" if score>=50 else "MEDIUM" if score>=25 else "LOW"
    evidence=sum(1 for key in ("attendance","salary","performance","pulse","training","turnover") if data.get(key))
    quality="SUFFICIENT" if evidence>=4 else "LIMITED"
    return {"risk_score":score,"risk_level":level,"risk_factors":factors,"recommended_actions":list({a['code']:a for a in actions}.values()),
            "model_type":MODEL_TYPE,"model_version":MODEL_VERSION,"data_quality":quality,
            "disclaimer":"Rules-based workforce signal, not a statistical prediction or employment decision."}
