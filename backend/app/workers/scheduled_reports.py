"""Celery beat worker for due report schedules."""
from datetime import date,datetime,timedelta,timezone
from app.core.config import settings
from app.services.reporting_service import execute_report,period_for

def _next(schedule,now):
 frequency=schedule["frequency"]
 if frequency=="DAILY":return now+timedelta(days=1)
 if frequency=="WEEKLY":return now+timedelta(days=7)
 month=now.month+1;year=now.year+(month>12);month=1 if month>12 else month;return now.replace(year=year,month=month,day=min(int(schedule.get("day_of_month") or 1),28))
def process_due_reports(db):
 now=datetime.now(timezone.utc);due=db.table("report_schedules").select("*").eq("is_active",True).lte("next_run_at",now.isoformat()).execute().data or [];result={"processed":0,"failed":0}
 for schedule in due:
  try:
   start,end=period_for(schedule["report_type"],date.today());execute_report(db,org_id=schedule["org_id"],report_type=schedule["report_type"],property_id=schedule.get("property_id"),generated_by=schedule.get("created_by"),period_start=start,period_end=end,schedule_id=schedule["id"],recipients=schedule.get("recipients") or []);db.table("report_schedules").update({"next_run_at":_next(schedule,now).isoformat(),"updated_at":now.isoformat()}).eq("id",schedule["id"]).execute();result["processed"]+=1
  except Exception:result["failed"]+=1
 return result
try:
 from app.celery_app import celery_app
 @celery_app.task(name="app.workers.scheduled_reports.run_scheduled_reports",autoretry_for=(Exception,),retry_backoff=True,max_retries=3)
 def run_scheduled_reports():
  from supabase import create_client
  return process_due_reports(create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY))
except ImportError:
 run_scheduled_reports=lambda:None
