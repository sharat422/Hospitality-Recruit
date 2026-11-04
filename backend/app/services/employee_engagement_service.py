"""Shared PWA/WhatsApp pulse submission and transparent engagement scoring."""
from __future__ import annotations
import secrets
from datetime import datetime
from fastapi import HTTPException

def rows(result):
    data=getattr(result,"data",None)
    return data if isinstance(data,list) else ([data] if isinstance(data,dict) else [])

def submit_pulse_response(db,*,survey:dict,employee:dict,score:int,comment:str|None,source:str)->dict:
    source=source.upper()
    if source not in {"PWA","WHATSAPP","WEB","ADMIN"}:raise HTTPException(422,"Unsupported survey channel")
    if source not in (survey.get("channels") or []):raise HTTPException(422,"Survey is not enabled for this channel")
    if int(score)<int(survey["scale_min"]) or int(score)>int(survey["scale_max"]):raise HTTPException(422,"Score outside survey scale")
    existing=rows(db.table("employee_pulse_participation").select("id").eq("survey_id",survey["id"]).eq("employee_id",employee["id"]).limit(1).execute())
    if existing:raise HTTPException(409,"Survey already answered")
    participation={"org_id":employee["org_id"],"survey_id":survey["id"],"employee_id":employee["id"],"channel":source}
    try:
        db.table("employee_pulse_participation").insert(participation).execute()
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(409,"Survey already answered") from exc
        raise
    anonymous=bool(survey.get("is_anonymous"))
    payload={"org_id":employee["org_id"],"survey_id":survey["id"],"employee_id":None if anonymous else employee["id"],
      "response_fingerprint":secrets.token_hex(32),"score":score,"comment":comment.strip() if comment else None,"source":source,
      "property_id":employee.get("active_property_id"),"department_id":employee.get("department_id")}
    saved=rows(db.table("employee_pulse_responses").insert(payload).execute())
    return {"id":saved[0].get("id") if saved else None,"survey_id":survey["id"],"recorded":True,"anonymous":anonymous,"source":source}

def calculate_engagement_score(data:dict)->dict:
    """Weighted operational score. Missing components are excluded, never treated as zero."""
    components=[]
    pulse=data.get("pulse_average")
    if pulse is not None:components.append({"code":"PULSE","score":max(0,min(100,float(pulse)/5*100)),"weight":40,"explanation":f"Identified pulse average {float(pulse):.1f}/5"})
    attendance=data.get("attendance_rate")
    if attendance is not None:components.append({"code":"ATTENDANCE","score":max(0,min(100,float(attendance))),"weight":20,"explanation":f"Validated attendance rate {float(attendance):.1f}%"})
    training=data.get("training_completion_rate")
    if training is not None:components.append({"code":"LEARNING","score":max(0,min(100,float(training))),"weight":20,"explanation":f"Assigned training completion {float(training):.1f}%"})
    recognitions=int(data.get("approved_recognitions") or 0)
    components.append({"code":"RECOGNITION","score":min(100,recognitions*25),"weight":20,"explanation":f"{recognitions} approved recognitions in the period"})
    weight=sum(x["weight"] for x in components);score=round(sum(x["score"]*x["weight"] for x in components)/weight,2) if weight else 0
    level="VERY_HIGH" if score>=80 else "HIGH" if score>=65 else "MODERATE" if score>=45 else "LOW"
    return {"engagement_score":score,"engagement_level":level,"score_components":components,
      "data_quality":"SUFFICIENT" if len(components)>=3 else "LIMITED","model_type":"RULES_BASED","model_version":"ENGAGEMENT_RULES_V1",
      "disclaimer":"Operational engagement indicator, not a psychological assessment or employment decision."}

def aggregate_comparison(responses:list[dict],group_key:str,min_group_size:int=5)->list[dict]:
    grouped={}
    for row in responses:
        key=row.get(group_key)
        if key:grouped.setdefault(str(key),[]).append(float(row["score"]))
    output=[]
    for key,scores in grouped.items():
        if len(scores)<min_group_size:output.append({group_key:key,"response_count":len(scores),"suppressed":True,"average_score":None})
        else:output.append({group_key:key,"response_count":len(scores),"suppressed":False,"average_score":round(sum(scores)/len(scores),2)})
    return sorted(output,key=lambda x:x[group_key])
