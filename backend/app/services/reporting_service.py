"""Reusable data collection, PDF rendering and multi-channel report delivery."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO
from typing import Any

from app.core.config import settings
from app.services.email_service import send_email_sync
from app.services.whatsapp_gateway import send_document

REPORT_TYPES = {"DAILY_HR","WEEKLY_RECRUITMENT","MONTHLY_WORKFORCE","PAYROLL","COMPLIANCE","ATTRITION","SOURCE","PROPERTY_COMPARISON"}
FINANCIAL_REPORTS = {"PAYROLL"}

def rows(result: Any) -> list[dict]:
 data=getattr(result,"data",None);return data if isinstance(data,list) else ([data] if isinstance(data,dict) else [])
def avg(values): return round(sum(values)/len(values),1) if values else None
def scoped(q,property_id): return q.eq("property_id",property_id) if property_id else q

def collect_report(db,report_type:str,org_id:str,property_id:str|None,start:date,end:date)->dict:
 if report_type not in REPORT_TYPES: raise ValueError("Unsupported report type")
 title=report_type.replace("_"," ").title(); sections=[]
 if report_type=="DAILY_HR":
  att=rows(scoped(db.table("attendance_daily_records").select("status,overtime_minutes").eq("org_id",org_id).eq("validation_status","VALIDATED").gte("attendance_date",start.isoformat()).lte("attendance_date",end.isoformat()),property_id).execute())
  leave=rows(scoped(db.table("leave_requests").select("status,total_days").eq("org_id",org_id).eq("status","APPROVED").lte("start_date",end.isoformat()).gte("end_date",start.isoformat()),property_id).execute())
  counts=Counter(str(x.get("status")) for x in att);sections=[{"title":"Attendance","metrics":{"Present":counts["PRESENT"],"Absent":counts["ABSENT"],"Missing punch":counts["MISSING_PUNCH"],"Overtime hours":round(sum(int(x.get("overtime_minutes") or 0) for x in att)/60,1)}},{"title":"Leave","metrics":{"Approved requests":len(leave),"Leave days":sum(float(x.get("total_days") or 0) for x in leave)}}]
 elif report_type in {"WEEKLY_RECRUITMENT","SOURCE"}:
  q=db.table("applications").select("status,source").eq("org_id",org_id).gte("created_at",start.isoformat()).lt("created_at",(end+timedelta(days=1)).isoformat());apps=rows(scoped(q,property_id).execute());stages=Counter(str(x.get("status") or "UNKNOWN").upper() for x in apps);sources=defaultdict(lambda:{"applications":0,"hires":0})
  for x in apps:k=str(x.get("source") or "UNKNOWN").upper();sources[k]["applications"]+=1;sources[k]["hires"]+=str(x.get("status")).upper()=="HIRED"
  sections=[{"title":"Funnel","metrics":{"Applications":len(apps),**dict(stages)}},{"title":"Sources","rows":[{"source":k,**v,"conversion_pct":round(v["hires"]*100/v["applications"],1)} for k,v in sources.items()]}]
 elif report_type=="PAYROLL":
  runs=rows(scoped(db.table("payroll_runs").select("id,status,period_year,period_month").eq("org_id",org_id).in_("status",["APPROVED","FINALIZED"]),property_id).execute());runs=[x for x in runs if start.replace(day=1)<=date(int(x["period_year"]),int(x["period_month"]),1)<=end.replace(day=1)];ids=[x["id"] for x in runs];items=rows(db.table("payroll_run_items").select("gross_inr,net_inr,employer_cost_inr,lop_inr,overtime_inr,status").in_("payroll_run_id",ids).eq("status","FINALIZED").execute()) if ids else []
  sections=[{"title":"Finalized Payroll","metrics":{"Employees paid":len(items),"Gross INR":sum(float(x.get("gross_inr") or 0) for x in items),"Net INR":sum(float(x.get("net_inr") or 0) for x in items),"Employer cost INR":sum(float(x.get("employer_cost_inr") or 0) for x in items),"LOP INR":sum(float(x.get("lop_inr") or 0) for x in items),"Overtime INR":sum(float(x.get("overtime_inr") or 0) for x in items)}}]
 elif report_type=="COMPLIANCE":
  jobs=rows(scoped(db.table("jobs").select("id").eq("org_id",org_id),property_id).execute());job_ids=[x["id"] for x in jobs];tasks=rows(db.table("compliance_tasks").select("status,due_date,task_type").eq("org_id",org_id).in_("job_id",job_ids).execute()) if job_ids else [];employee_query=db.table("users").select("id").eq("org_id",org_id);employee_query=employee_query.eq("active_property_id",property_id) if property_id else employee_query;employees=rows(employee_query.execute());employee_ids=[x["id"] for x in employees];certs=rows(db.table("employee_certifications").select("status,expiry_date").eq("org_id",org_id).in_("employee_id",employee_ids).lte("expiry_date",end.isoformat()).execute()) if employee_ids else [];sections=[{"title":"Compliance","metrics":{"Open tasks":sum(str(x.get("status")).upper() in {"PENDING","IN_PROGRESS"} for x in tasks),"Overdue tasks":sum(x.get("due_date") and str(x["due_date"])[:10]<date.today().isoformat() for x in tasks),"Expired/due certificates":len(certs)}}]
 elif report_type=="ATTRITION":
  q=db.table("employee_turnover_history").select("event_type,reason_category").eq("org_id",org_id).gte("effective_date",start.isoformat()).lte("effective_date",end.isoformat());turn=rows(scoped(q,property_id).execute());riskq=db.table("employee_retention_risk_scores").select("risk_level,risk_score").eq("org_id",org_id).is_("superseded_at","null");risks=rows(scoped(riskq,property_id).execute());sections=[{"title":"Attrition","metrics":{"Exits":len(turn),**dict(Counter(str(x.get("event_type")) for x in turn))}},{"title":"Turnover Risk","metrics":{"Assessed":len(risks),"High/Critical":sum(str(x.get("risk_level")) in {"HIGH","CRITICAL"} for x in risks),"Average risk":avg([float(x.get("risk_score") or 0) for x in risks])}}]
 else:
  users=rows(db.table("users").select("id,active_property_id,department_id,employment_status,role").eq("org_id",org_id).execute());users=[x for x in users if x.get("active_property_id") and str(x.get("employment_status") or "ACTIVE")=="ACTIVE" and str(x.get("role")).upper() not in {"OWNER","GROUP_ADMIN_HR","CANDIDATE"} and (not property_id or x.get("active_property_id")==property_id)];props=rows(db.table("properties").select("id,name").eq("org_id",org_id).execute());by=Counter(x.get("active_property_id") for x in users);eng=rows(scoped(db.table("employee_engagement_scores").select("engagement_score").eq("org_id",org_id).is_("superseded_at","null"),property_id).execute());sections=[{"title":"Workforce","metrics":{"Headcount":len(users),"Average engagement":avg([float(x.get("engagement_score") or 0) for x in eng])}},{"title":"Property Comparison","rows":[{"property":p["name"],"headcount":by[p["id"]]} for p in props if p["id"] in by]}]
 return {"title":title,"report_type":report_type,"period":{"start":start.isoformat(),"end":end.isoformat()},"generated_at":datetime.now(timezone.utc).isoformat(),"sections":sections,"data_source":"LIVE_DATABASE"}

def render_pdf(data:dict)->bytes:
 from reportlab.lib.pagesizes import A4
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
 from reportlab.lib import colors
 out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,title=data["title"]);styles=getSampleStyleSheet();story=[Paragraph(escape(data["title"]),styles["Title"]),Paragraph(f"Period: {data['period']['start']} to {data['period']['end']} · Live database",styles["Normal"]),Spacer(1,14)]
 for section in data["sections"]:
  story += [Paragraph(escape(section["title"]),styles["Heading2"])]
  records=[["Metric","Value"]]+[[str(k),str(v if v is not None else "Not available")] for k,v in section.get("metrics",{}).items()]
  if section.get("rows"):
   keys=list(section["rows"][0]);records=[keys]+[[str(row.get(k,"")) for k in keys] for row in section["rows"]]
  table=Table(records,repeatRows=1);table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#047857")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.25,colors.grey),("PADDING",(0,0),(-1,-1),6)]));story += [table,Spacer(1,14)]
 doc.build(story);return out.getvalue()

def deliver_report(run:dict,recipients:list[dict])->list[dict]:
 url=f"{settings.API_PUBLIC_BASE_URL}/api/v1/reports/public/{run['download_token']}.pdf";results=[]
 for recipient in recipients:
  channel=str(recipient.get("channel") or "EMAIL").upper();target=recipient.get("recipient","");reference=None
  if channel=="EMAIL":reference="smtp" if send_email_sync(target,f"HospRecruit: {run['report_type'].replace('_',' ').title()}",f'<p>Your report is ready.</p><p><a href="{url}">Download PDF</a></p>') else None
  elif channel=="WHATSAPP":reference=send_document(target,url,"Your HospRecruit report is ready.",f"{run['report_type'].lower()}.pdf")
  results.append({"channel":channel,"recipient":target,"status":"SENT" if reference else "FAILED","provider_reference":reference})
 return results

def period_for(report_type:str,run_date:date)->tuple[date,date]:
 if report_type=="DAILY_HR": return run_date,run_date
 if report_type in {"WEEKLY_RECRUITMENT","SOURCE"}: return run_date-timedelta(days=6),run_date
 first=run_date.replace(day=1);return first,run_date

def execute_report(db,*,org_id:str,report_type:str,property_id:str|None,generated_by:str|None,
                   period_start:date,period_end:date,schedule_id:str|None=None,recipients:list[dict]|None=None)->dict:
 payload=collect_report(db,report_type,org_id,property_id,period_start,period_end)
 inserted=rows(db.table("report_runs").insert({"org_id":org_id,"schedule_id":schedule_id,"report_type":report_type,"property_id":property_id,"period_start":period_start.isoformat(),"period_end":period_end.isoformat(),"status":"PROCESSING","report_data":payload,"generated_by":generated_by}).execute())
 if not inserted: raise RuntimeError("Could not create report run")
 run=inserted[0];deliveries=deliver_report(run,recipients or [])
 for delivery in deliveries: db.table("report_deliveries").insert({"org_id":org_id,"report_run_id":run["id"],**delivery,"attempt_count":1,"delivered_at":datetime.now(timezone.utc).isoformat() if delivery["status"]=="SENT" else None}).execute()
 final="COMPLETED" if all(x["status"]=="SENT" for x in deliveries) else ("PARTIAL" if any(x["status"]=="SENT" for x in deliveries) else ("FAILED" if deliveries else "COMPLETED"))
 db.table("report_runs").update({"status":final,"completed_at":datetime.now(timezone.utc).isoformat()}).eq("id",run["id"]).execute();return {**run,"status":final,"report_data":payload,"deliveries":deliveries}
