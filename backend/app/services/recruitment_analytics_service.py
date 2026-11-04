"""Deterministic recruitment metrics computed only from persisted database rows."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
STAGES=['APPLIED','SCREENED','SHORTLISTED','INTERVIEW','SELECTED','OFFER','OFFER_ACCEPTED','ONBOARDING','HIRED']
RANK={stage:i for i,stage in enumerate(STAGES)}
def dt(value):
 if not value:return None
 try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).replace(tzinfo=timezone.utc) if '+' not in str(value)[10:] and not str(value).endswith('Z') else datetime.fromisoformat(str(value).replace('Z','+00:00'))
 except (ValueError,TypeError):return None
def days(start,end):
 a,b=dt(start),dt(end);return max(0,(b-a).total_seconds()/86400) if a and b else None
def pct(n,d):return round(n*100/d,1) if d else 0.0
def normalize(status):
 value=str(status or 'APPLIED').upper();return 'APPLIED' if value in {'DRAFT','SUBMITTED'} else value
def aggregate(*,applications,jobs,costs=None,ghosting=None,referrals=None,performance=None,candidate_users=None):
 costs=costs or [];ghosting=ghosting or [];referrals=referrals or [];performance=performance or [];candidate_users=candidate_users or {}
 exact=Counter(normalize(x.get('status')) for x in applications);funnel=[]
 for stage in STAGES:
  reached=sum(1 for x in applications if RANK.get(normalize(x.get('status')),-1)>=RANK[stage]);funnel.append({'stage':stage,'count':reached,'conversion_from_applied_pct':pct(reached,len(applications))})
 hires=[x for x in applications if normalize(x.get('status'))=='HIRED'];offers=[x for x in applications if RANK.get(normalize(x.get('status')),-1)>=RANK['OFFER']];accepted=[x for x in applications if RANK.get(normalize(x.get('status')),-1)>=RANK['OFFER_ACCEPTED']];interviewed=[x for x in applications if RANK.get(normalize(x.get('status')),-1)>=RANK['INTERVIEW']];interview_converted=[x for x in applications if RANK.get(normalize(x.get('status')),-1)>=RANK['SELECTED']]
 hire_times=[v for x in hires if (v:=days(x.get('created_at'),x.get('hired_at')))!=None]
 job_apps=defaultdict(list)
 for x in hires:
  if x.get('job_id'):job_apps[x['job_id']].append(x)
 fill_times=[]
 for job in jobs:
  hired=sorted(job_apps.get(job['id'],[]),key=lambda x:x.get('hired_at') or '')
  needed=max(1,int(job.get('openings_count') or 1))
  if len(hired)>=needed:
   value=days(job.get('approved_at') or job.get('created_at'),job.get('filled_at') or hired[needed-1].get('hired_at'))
   if value is not None:fill_times.append(value)
 source=defaultdict(lambda:{'applications':0,'hires':0})
 for x in applications:
  key=str(x.get('source') or 'UNKNOWN').upper();source[key]['applications']+=1;source[key]['hires']+=normalize(x.get('status'))=='HIRED'
 source_rows=[{'source':k,**v,'conversion_pct':pct(v['hires'],v['applications'])} for k,v in sorted(source.items(),key=lambda i:i[1]['applications'],reverse=True)]
 total_cost=round(sum(float(x.get('amount_inr') or 0) for x in costs),2)
 high_risk=sum(1 for x in ghosting if str(x.get('risk_level')).upper() in {'HIGH','CRITICAL'})
 referral_applied=sum(1 for x in referrals if str(x.get('status')).upper() in {'APPLIED','SHORTLISTED','HIRED','REWARDED','BONUS_PAID'});referral_hired=sum(1 for x in referrals if str(x.get('status')).upper() in {'HIRED','REWARDED','BONUS_PAID'})
 hired_employee_ids={candidate_users.get(x.get('candidate_id')) for x in hires}-{None};ratings=[float(x.get('overall_score') or float(x.get('rating') or 0)*20) for x in performance if x.get('employee_id') in hired_employee_ids and (x.get('overall_score') is not None or x.get('rating') is not None)]
 return {'applications':len(applications),'hires':len(hires),'active_jobs':sum(1 for x in jobs if str(x.get('status')).lower()=='open'),'funnel':funnel,'stage_counts':dict(exact),'source_performance':source_rows,'time_to_hire_days':round(sum(hire_times)/len(hire_times),1) if hire_times else None,'time_to_hire_sample':len(hire_times),'time_to_fill_days':round(sum(fill_times)/len(fill_times),1) if fill_times else None,'time_to_fill_sample':len(fill_times),'interview_conversion_pct':pct(len(interview_converted),len(interviewed)),'offer_acceptance_pct':pct(len(accepted),len(offers)),'ghosting':{'high_or_critical':high_risk,'assessed':len(ghosting),'rate_pct':pct(high_risk,len(ghosting))},'referrals':{'applied':referral_applied,'hired':referral_hired,'conversion_pct':pct(referral_hired,referral_applied)},'cost':{'total_inr':total_cost,'cost_per_hire_inr':round(total_cost/len(hires),2) if hires else None,'entries':len(costs)},'quality_of_hire':{'average_score':round(sum(ratings)/len(ratings),1) if ratings else None,'reviewed_hires':len(ratings),'method':'latest persisted performance review score; unavailable until hired employees are reviewed'}}
