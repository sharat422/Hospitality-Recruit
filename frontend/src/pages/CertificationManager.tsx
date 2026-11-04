import { AlertTriangle,Award,CheckCircle2,Loader2,Plus,RefreshCw,Upload } from 'lucide-react';
import { useEffect,useState } from 'react';
import { apiClient } from '../lib/api';

type CertType = { id:string; code:string; name:string; category:string; is_fssai_managed:boolean }
type Cert = { id:string; source_type:string; certification_code:string; certification_name:string; certificate_number?:string; expiry_date?:string; status:string; days_remaining?:number; file_name?:string }
type Requirement = { id:string; role_title:string; is_mandatory:boolean; required_before_start:boolean; certification_types?:CertType }
const input='min-h-11 w-full rounded border border-slate-300 bg-white px-3 text-sm focus:border-emerald-600 focus:outline-none'
const btn='inline-flex min-h-11 items-center justify-center gap-2 rounded bg-emerald-700 px-4 text-sm font-semibold text-white disabled:opacity-50'

function Status({value}:{value:string}) {
  const color=value==='VERIFIED'?'bg-emerald-100 text-emerald-800':value==='EXPIRED'?'bg-red-100 text-red-800':value==='RENEWAL_DUE'?'bg-amber-100 text-amber-800':'bg-slate-100 text-slate-700'
  return <span className={`rounded px-2 py-1 text-xs font-semibold ${color}`}>{value.split('_').join(' ')}</span>
}

export default function CertificationManager() {
  const [tab,setTab]=useState<'employee'|'requirements'|'settings'>('employee')
  const [employeeId,setEmployeeId]=useState('')
  const [types,setTypes]=useState<CertType[]>([])
  const [certs,setCerts]=useState<Cert[]>([])
  const [compliance,setCompliance]=useState<any>(null)
  const [requirements,setRequirements]=useState<Requirement[]>([])
  const [loading,setLoading]=useState(false)
  const [message,setMessage]=useState('')
  const [form,setForm]=useState({certification_code:'FIRE_SAFETY',certificate_number:'',issuing_authority:'',issue_date:'',expiry_date:'',file:null as File|null,renewal_of:''})
  const [req,setReq]=useState({role_title:'',certification_code:'FIRE_SAFETY',is_mandatory:true,required_before_start:false})
  const [settings,setSettings]=useState({reminder_days:[90,60,30,7,0],notify_employee:true,notify_manager:true,preferred_channel:'SMS'})

  useEffect(()=>{ void Promise.all([
    apiClient.get('/certifications/types').then(r=>setTypes(r.data)),
    apiClient.get('/certifications/requirements').then(r=>setRequirements(r.data)),
    apiClient.get('/certifications/alert-settings').then(r=>setSettings(r.data)),
  ]).catch(()=>setMessage('Could not load certification settings. Please retry.')) },[])

  const loadEmployee=async()=>{if(!employeeId)return;setLoading(true);setMessage('');try{const [a,b]=await Promise.all([
    apiClient.get(`/certifications/employees/${employeeId}`),apiClient.get(`/certifications/employees/${employeeId}/compliance`)
  ]);setCerts(a.data);setCompliance(b.data)}catch(e:any){setMessage(e.response?.data?.detail||'Could not load employee certifications')}finally{setLoading(false)}}

  const createCert=async()=>{if(!employeeId||!form.certification_code)return;setLoading(true);setMessage('');try{
    const payload:any={...form,file:undefined,filename:form.file?.name,content_type:form.file?.type||'application/pdf',renewal_of:form.renewal_of||undefined}
    const {data}=await apiClient.post(`/certifications/employees/${employeeId}`,payload)
    if(form.file&&data.upload){const uploadResponse=await fetch(data.upload.upload_url,{method:'PUT',headers:data.upload.upload_headers,body:form.file});if(!uploadResponse.ok)throw new Error('Certificate upload failed');await apiClient.patch(`/certifications/${data.id}/confirm-upload`,{storage_key:data.upload.storage_key,file_name:form.file.name,mime_type:form.file.type||'application/pdf'})}
    setMessage('Certificate submitted for verification');setForm({...form,certificate_number:'',issuing_authority:'',issue_date:'',expiry_date:'',file:null,renewal_of:''});await loadEmployee()
  }catch(e:any){setMessage(e.response?.data?.detail||'Certificate upload failed')}finally{setLoading(false)}}

  const verify=async(cert:Cert,status:'VERIFIED'|'REJECTED')=>{if(cert.source_type==='FSSAI')await apiClient.patch(`/fssai/certificates/${cert.id}/verify`,{status:status==='VERIFIED'?'ACTIVE':'REJECTED'});else await apiClient.patch(`/certifications/${cert.id}/verify`,{status});await loadEmployee()}
  const addRequirement=async()=>{await apiClient.post('/certifications/requirements',req);const r=await apiClient.get('/certifications/requirements');setRequirements(r.data);setMessage('Role requirement saved')}
  const saveSettings=async()=>{const r=await apiClient.put('/certifications/alert-settings',settings);setSettings(r.data);setMessage('Reminder settings saved')}

  return <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
    <header><h1 className="text-2xl font-bold text-slate-900">Certification Manager</h1><p className="mt-1 text-sm text-slate-500">Role requirements, verification, renewals and expiry alerts</p></header>
    <div className="flex gap-1 border-b">{(['employee','requirements','settings'] as const).map(t=><button key={t} onClick={()=>setTab(t)} className={`min-h-11 px-4 text-sm font-medium capitalize ${tab===t?'border-b-2 border-emerald-700 text-emerald-800':'text-slate-500'}`}>{t}</button>)}</div>
    {message&&<div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{message}</div>}

    {tab==='employee'&&<>
      <section className="flex flex-col gap-3 border-b pb-5 sm:flex-row"><input className={input} value={employeeId} onChange={e=>setEmployeeId(e.target.value)} placeholder="Employee UUID"/><button className={btn} onClick={loadEmployee} disabled={loading||!employeeId}>{loading?<Loader2 className="animate-spin" size={17}/>:<RefreshCw size={17}/>}Load employee</button></section>
      {compliance&&<section className={`border-l-4 p-4 ${compliance.compliant?'border-emerald-600 bg-emerald-50':'border-red-600 bg-red-50'}`}><div className="flex items-center gap-2 font-semibold">{compliance.compliant?<CheckCircle2 size={18}/>:<AlertTriangle size={18}/>} {compliance.job_title||'Unassigned role'}: {compliance.compliant?'Compliant':'Missing mandatory certificates'}</div>{compliance.missing_mandatory?.map((m:any)=><span key={m.code} className="mr-2 mt-2 inline-block rounded bg-white px-2 py-1 text-xs">{m.name}</span>)}</section>}
      <section className="grid gap-4 lg:grid-cols-[1fr_380px]"><div className="overflow-x-auto border"><table className="w-full text-sm"><thead className="bg-slate-50"><tr>{['Certificate','Number','Expiry','Status','Actions'].map(h=><th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead><tbody>{certs.map(c=><tr key={`${c.source_type}-${c.id}`} className="border-t"><td className="px-3 py-3 font-medium">{c.certification_name}<div className="text-xs text-slate-400">{c.source_type}</div></td><td className="px-3">{c.certificate_number||'—'}</td><td className="px-3">{c.expiry_date||'No expiry'}{c.days_remaining!=null&&<div className="text-xs text-slate-500">{c.days_remaining} days</div>}</td><td className="px-3"><Status value={c.status}/></td><td className="px-3">{c.status==='PENDING_VERIFICATION'&&<div className="flex gap-2"><button onClick={()=>verify(c,'VERIFIED')} className="text-emerald-700">Verify</button><button onClick={()=>verify(c,'REJECTED')} className="text-red-700">Reject</button></div>}{c.source_type==='EMPLOYEE_CERT'&&['EXPIRED','RENEWAL_DUE'].includes(c.status)&&<button onClick={()=>setForm({...form,certification_code:c.certification_code,renewal_of:c.id})} className="text-blue-700">Renew</button>}{c.source_type==='FSSAI'&&['EXPIRED','RENEWAL_DUE'].includes(c.status)&&<span className="text-xs text-slate-500">Renew in India Compliance</span>}</td></tr>)}</tbody></table>{certs.length===0&&<p className="p-8 text-center text-sm text-slate-400">No certificates loaded.</p>}</div>
        <div className="space-y-3 border p-4"><h2 className="font-semibold">{form.renewal_of?'Renew certificate':'Add certificate'}</h2><select className={input} value={form.certification_code} onChange={e=>setForm({...form,certification_code:e.target.value})}>{types.filter(t=>!t.is_fssai_managed).map(t=><option key={t.code} value={t.code}>{t.name}</option>)}</select><input className={input} value={form.certificate_number} onChange={e=>setForm({...form,certificate_number:e.target.value})} placeholder="Certificate number"/><input className={input} value={form.issuing_authority} onChange={e=>setForm({...form,issuing_authority:e.target.value})} placeholder="Issuing authority"/><label className="text-xs text-slate-500">Issue date<input type="date" className={`${input} mt-1`} value={form.issue_date} onChange={e=>setForm({...form,issue_date:e.target.value})}/></label><label className="text-xs text-slate-500">Expiry date<input type="date" className={`${input} mt-1`} value={form.expiry_date} onChange={e=>setForm({...form,expiry_date:e.target.value})}/></label><label className="flex min-h-20 cursor-pointer items-center justify-center gap-2 border border-dashed text-sm"><Upload size={17}/>{form.file?.name||'Upload PDF or image'}<input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" className="hidden" onChange={e=>setForm({...form,file:e.target.files?.[0]||null})}/></label><button className={`${btn} w-full`} onClick={createCert} disabled={loading}>Submit for verification</button><p className="text-xs text-slate-500">FSSAI, Food Hygiene and FoSTaC renewals are managed in India Compliance.</p></div>
      </section></>}

    {tab==='requirements'&&<div className="grid gap-5 lg:grid-cols-[360px_1fr]"><section className="space-y-3 border p-4"><h2 className="font-semibold">Add role requirement</h2><input className={input} value={req.role_title} onChange={e=>setReq({...req,role_title:e.target.value})} placeholder="Role title, e.g. Commis Chef"/><select className={input} value={req.certification_code} onChange={e=>setReq({...req,certification_code:e.target.value})}>{types.map(t=><option key={t.code} value={t.code}>{t.name}</option>)}</select><label className="flex gap-2 text-sm"><input type="checkbox" checked={req.is_mandatory} onChange={e=>setReq({...req,is_mandatory:e.target.checked})}/>Mandatory</label><label className="flex gap-2 text-sm"><input type="checkbox" checked={req.required_before_start} onChange={e=>setReq({...req,required_before_start:e.target.checked})}/>Required before start</label><button className={`${btn} w-full`} onClick={addRequirement} disabled={!req.role_title}><Plus size={17}/>Add requirement</button></section><section className="border"><div className="border-b p-3 font-semibold">Configured requirements</div>{requirements.map(r=><div key={r.id} className="flex items-center justify-between border-b p-3 text-sm"><div><strong>{r.role_title}</strong><div className="text-slate-500">{r.certification_types?.name}</div></div><span>{r.is_mandatory?'Mandatory':'Optional'}</span></div>)}</section></div>}

    {tab==='settings'&&<section className="max-w-xl space-y-4 border p-5"><h2 className="flex items-center gap-2 font-semibold"><Award size={18}/>Expiry reminders</h2><label className="text-sm">Intervals in days<input className={`${input} mt-1`} value={settings.reminder_days.join(', ')} onChange={e=>setSettings({...settings,reminder_days:e.target.value.split(',').map(v=>Number(v.trim())).filter(v=>Number.isFinite(v))})}/></label><select className={input} value={settings.preferred_channel} onChange={e=>setSettings({...settings,preferred_channel:e.target.value})}><option>SMS</option><option>WHATSAPP</option><option>BOTH</option></select><label className="flex gap-2"><input type="checkbox" checked={settings.notify_employee} onChange={e=>setSettings({...settings,notify_employee:e.target.checked})}/>Notify employee</label><label className="flex gap-2"><input type="checkbox" checked={settings.notify_manager} onChange={e=>setSettings({...settings,notify_manager:e.target.checked})}/>Notify manager</label><button className={btn} onClick={saveSettings}>Save settings</button></section>}
  </div>
}
