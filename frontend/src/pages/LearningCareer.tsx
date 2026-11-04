import { BookOpen,Briefcase,GraduationCap,Route,Target } from 'lucide-react'
import { useEffect,useMemo,useState } from 'react'
import apiClient from '../lib/api'
import { useRBAC } from '../lib/RBACContext'

type Row = Record<string, any>
const tabs = ['My Learning', 'Course Catalog', 'Skills & Gaps', 'Career Path', 'Internal Jobs'] as const

export default function LearningCareer() {
  const [tab, setTab] = useState<typeof tabs[number]>('My Learning')
  const [courses,setCourses]=useState<Row[]>([]), [learning,setLearning]=useState<Row[]>([])
  const [pathways,setPathways]=useState<Row[]>([]), [jobs,setJobs]=useState<Row[]>([])
  const [loading,setLoading]=useState(true), [error,setError]=useState('')
  const { can } = useRBAC()
  useEffect(()=>{(async()=>{try{
    const [c,l,p,j]=await Promise.all([
      apiClient.get('/learning-career/courses'),apiClient.get('/learning-career/my-learning'),
      apiClient.get('/learning-career/pathways'),apiClient.get('/learning-career/internal-jobs')])
    setCourses(c.data||[]);setLearning(l.data||[]);setPathways(p.data||[]);setJobs(j.data||[])
  }catch(e:any){setError(e.response?.data?.detail||'Could not load learning data')}finally{setLoading(false)}})()},[])
  const completed=learning.filter(x=>x.status==='COMPLETED').length
  const assigned=learning.filter(x=>x.status!=='COMPLETED'&&x.status!=='CANCELLED').length
  const gaps=useMemo(()=>pathways.flatMap(p=>(p.career_pathway_steps||[]).flatMap((s:Row)=>s.required_skills||[])),[pathways])

  async function updateProgress(id:string,value:number){
    await apiClient.patch(`/learning-career/enrollments/${id}/progress`,{progress_pct:value})
    setLearning(items=>items.map(x=>x.id===id?{...x,progress_pct:value,status:value===100?'COMPLETED':'IN_PROGRESS'}:x))
  }
  if(loading)return <div className="p-8 text-sm text-gray-500">Loading learning and career data…</div>
  return <div className="mx-auto max-w-7xl space-y-5">
    <header><h1 className="text-2xl font-bold text-gray-900">Learning & Career</h1><p className="mt-1 text-sm text-gray-600">Build hospitality skills and track transparent promotion readiness.</p></header>
    {error&&<div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Metric label="Active courses" value={assigned}/><Metric label="Completed" value={completed}/><Metric label="Career pathways" value={pathways.length}/><Metric label="Internal roles" value={jobs.length}/>
    </section>
    <div className="overflow-x-auto border-b border-gray-200"><div className="flex min-w-max gap-1">{tabs.map(t=><button key={t} onClick={()=>setTab(t)} className={`px-4 py-3 text-sm font-medium ${tab===t?'border-b-2 border-purple-600 text-purple-700':'text-gray-600'}`}>{t}</button>)}</div></div>
    {tab==='My Learning'&&<Grid empty="No courses assigned.">{learning.map(row=><article key={row.id} className="rounded-md border border-gray-200 bg-white p-4"><div className="flex justify-between gap-3"><div><h2 className="font-semibold">{row.training_name}</h2><p className="mt-1 text-xs text-gray-500">{row.training_courses?.delivery_type||row.category} · Due {row.due_date||'not set'}</p></div><Badge value={row.status}/></div><div className="mt-4 h-2 rounded bg-gray-100"><div className="h-2 rounded bg-purple-600" style={{width:`${row.progress_pct||0}%`}}/></div><div className="mt-3 flex justify-between text-xs text-gray-500"><span>{row.progress_pct||0}% complete</span>{row.status!=='COMPLETED'&&<button onClick={()=>updateProgress(row.id,Math.min(100,(row.progress_pct||0)+25))} className="font-medium text-purple-700">Continue</button>}</div></article>)}</Grid>}
    {tab==='Course Catalog'&&<Grid empty="No active courses.">{courses.map(row=><article key={row.id} className="rounded-md border border-gray-200 bg-white p-4"><BookOpen className="h-5 w-5 text-purple-600"/><h2 className="mt-3 font-semibold">{row.title}</h2><p className="mt-1 line-clamp-2 text-sm text-gray-600">{row.description||'Hospitality learning course'}</p><p className="mt-3 text-xs text-gray-500">{row.delivery_type} · {row.duration_minutes} minutes · Pass {row.pass_score}%</p>{can('training.manage')&&<span className="mt-3 inline-block text-xs font-medium text-purple-700">Manager assignment available via API</span>}</article>)}</Grid>}
    {tab==='Skills & Gaps'&&<section className="rounded-md border border-gray-200 bg-white p-5"><div className="flex items-center gap-2 font-semibold"><Target className="h-5 w-5 text-purple-600"/>Required pathway skills</div><div className="mt-4 flex flex-wrap gap-2">{gaps.length?gaps.map((g:any,i)=><span key={i} className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-800">{g.name||g.skill_name||g.skill_id} · level {g.min_proficiency||1}</span>):<p className="text-sm text-gray-500">Select a configured pathway to calculate skill gaps.</p>}</div></section>}
    {tab==='Career Path'&&<Grid empty="No career pathways configured.">{pathways.map(path=><article key={path.id} className="rounded-md border border-gray-200 bg-white p-4"><Route className="h-5 w-5 text-purple-600"/><h2 className="mt-3 font-semibold">{path.name}</h2><p className="text-xs text-gray-500">{path.department_name}</p><ol className="mt-4 space-y-3">{(path.career_pathway_steps||[]).sort((a:Row,b:Row)=>a.step_order-b.step_order).map((s:Row)=><li key={s.id} className="border-l-2 border-purple-200 pl-3 text-sm"><strong>{s.current_role_title}</strong> → {s.target_role_title}<div className="text-xs text-gray-500">Performance ≥ {s.minimum_performance_score} · {s.minimum_tenure_months} months</div></li>)}</ol></article>)}</Grid>}
    {tab==='Internal Jobs'&&<Grid empty="No internal jobs open.">{jobs.map(job=><article key={job.id} className="rounded-md border border-gray-200 bg-white p-4"><Briefcase className="h-5 w-5 text-purple-600"/><h2 className="mt-3 font-semibold">{job.title}</h2><p className="mt-2 text-sm text-gray-600">₹{Number(job.salary_min_inr||0).toLocaleString('en-IN')} – ₹{Number(job.salary_max_inr||0).toLocaleString('en-IN')}</p><Badge value={job.visibility}/></article>)}</Grid>}
    <p className="text-xs text-gray-500">Readiness scores are advisory. Promotions and internal moves require manager approval.</p>
  </div>
}
function Metric({label,value}:{label:string,value:number}){return <div className="rounded-md border border-gray-200 bg-white p-4"><div className="text-xs text-gray-500">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div></div>}
function Badge({value}:{value:string}){return <span className="inline-flex rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs font-medium text-gray-700">{String(value||'').replaceAll('_',' ')}</span>}
function Grid({children,empty}:{children:any,empty:string}){return <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{children?.length?children:<div className="col-span-full rounded-md border border-dashed border-gray-300 p-10 text-center text-sm text-gray-500"><GraduationCap className="mx-auto mb-2 h-6 w-6"/>{empty}</div>}</section>}
